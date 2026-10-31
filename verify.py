# 확인하기: 학생이 버튼을 누르면 찍은 사진 한 장을 그 카드의 '완료 기준'(시범 영상에서 그 단계가 끝난 순간 사진 + 교사가 쓴 기준 문장)과 비교한다.
# 동작의 질(자세)은 보지 않고 결과 상태만 본다. 결과: done(됐어요) / not_yet(아직) / different(달라요) / unclear(잘 안 보여요).
# 판단은 모델이, 마지막 정리는 코드가 한다(확신이 낮으면 unclear, 안내가 길거나 비면 기본 문장). 사진은 저장하지 않는다.
import json, re
from pathlib import Path
import pipeline
from coach import local_client

RESULTS = ("done", "not_yet", "different", "unclear")
MIN_CONF = 0.5
HINT_MAX = 30
PROMPT = """You check one step of a hands-on task for a learner with an intellectual disability.
Step to check: "{en}" (Korean: "{ko}"){crit}
Image A shows how things looked BEFORE this step in the teacher's demonstration.
Image B shows how things should look AFTER this step is done correctly (the target).
Image C is the learner's photo, taken now.
Compare C with B (and A). Judge only the result state of THIS step, not how the hands move or anything else.
Answer only JSON: {{"result": "done|not_yet|different|unclear", "hint_ko": "...", "hint_en": "...", "confidence": 0.0-1.0}}
- done: C shows the same result as B for this step (small differences in colour, angle, position or objects are fine).
- not_yet: C still looks like A, or the step is only partly done.
- different: the step was done, but the result clearly differs from B in a way that matters (wrong side, wrong amount, wrong place).
- unclear: you cannot see the relevant objects or hands well enough.
- hint_ko / hint_en: if not done, ONE short plain instruction (Korean ending in ~세요, at most 20 characters) saying what to do. If done, an empty string."""


def fallback_hint(result, card):
    """모델 안내가 없거나 길면 쓰는 기본 문장"""
    if result == "unclear":
        return "손과 물건이 보이게 다시 찍어요.", "Show your hands and the objects, then try again."
    if result == "done":
        return "", ""
    return card.get("ko", ""), card.get("en", "")


def tidy(d, card):
    """모델 답 → 화면에 쓸 결과. 코드가 마지막으로 정리한다"""
    result = d.get("result") if d.get("result") in RESULTS else "unclear"
    try:
        conf = max(0.0, min(1.0, float(d.get("confidence", 0))))
    except (TypeError, ValueError):
        conf = 0.0
    if result != "unclear" and conf < MIN_CONF:  # 확신이 낮으면 판단하지 않는다(학생을 헷갈리게 하지 않게)
        result = "unclear"
    ko, en = str(d.get("hint_ko") or "").strip(), str(d.get("hint_en") or "").strip()
    fk, fe = fallback_hint(result, card)
    if result == "done":
        ko, en = "", ""
    elif result == "unclear" or not ko or len(ko) > HINT_MAX:
        ko, en = fk, fe
    elif not en or len(en) > 60:
        en = fe
    return {"result": result, "hint_ko": ko, "hint_en": en, "confidence": round(conf, 2)}


def parse(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}


def ask(card, before, after, photo, local=False):
    """before·after 는 데이터 URL(카드 시작·끝 장면), photo 는 학생 사진 데이터 URL. (모델 답 dict, 비용)"""
    crit = f'\nThe teacher\'s success criterion for this step: "{card["check"]}"' if card.get("check") else ""
    text = PROMPT.format(en=card.get("en", ""), ko=card.get("ko", ""), crit=crit)
    imgs = [("Image A (before)", before), ("Image B (target, after)", after), ("Image C (learner now)", photo)]
    if local:  # 이 맥의 Glimmer: 답 첫머리를 채워 긴 생각 글을 건너뛴다
        content = [x for label, url in imgs for x in ({"type": "text", "text": label}, {"type": "image_url", "image_url": {"url": url}})]
        content.append({"type": "text", "text": text})
        head = '{"result": "'
        r = local_client.chat.completions.create(model="glimmer", max_tokens=120, temperature=0,
                                                 messages=[{"role": "user", "content": content}, {"role": "assistant", "content": head}])
        body = r.choices[0].message.content or ""
        return parse(body if body.lstrip().startswith("{") else head + body), 0.0
    content = [x for label, url in imgs for x in ({"type": "input_text", "text": label}, {"type": "input_image", "image_url": url})]
    content.append({"type": "input_text", "text": text})
    r = pipeline.client.responses.create(model=pipeline.STEP_MODEL, input=[{"role": "user", "content": content}], store=False,
                                         reasoning={"effort": "minimal"})
    u = r.usage
    return parse(r.output_text), u.input_tokens * pipeline.PRICE_IN + u.output_tokens * pipeline.PRICE_OUT


def after_t(d, card):
    """완료 기준 시각: 교사가 고른 시각, 없으면 카드가 끝난 뒤 다음 카드 전의 빈 시간(손이 결과를 가리지 않는 때가 많다)"""
    if card.get("done_t") is not None:
        return card["done_t"]
    data = json.loads((d / "cards.json").read_text())
    cs = data["cards"]
    i = next((k for k, c in enumerate(cs) if c["n"] == card["n"]), None)
    nxt = cs[i + 1]["start"] if i is not None and i + 1 < len(cs) else data.get("duration", card["end"])
    return min(card["end"] + 2, nxt - 1) if nxt - card["end"] >= 2 else card["end"]


SIMILAR = 0.05  # 시작·끝 장면의 평균 밝기 차이가 이보다 작으면 '결과가 비슷해 보이는 단계'(냅킨: 뒤집기 0.045, 끝 넣기 0.012)


def similarity(d, card):
    """시작·완료 기준 장면이 얼마나 다른지(0~1). 작으면 사진만으로는 됐는지 가르기 어렵다 → 기준 문장을 쓰게 한다"""
    from PIL import Image, ImageChops, ImageStat
    a, b = (Image.open(reference(d, card, w)).convert("L").resize((48, 27)) for w in ("before", "after"))
    return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] / 255


def reference(d, card, which):
    """카드의 시작(before)·완료 기준(after) 장면 사진. 영상에서 한 번 뽑아 두고, 영상이 없으면(보관됨) 카드 사진으로 대신한다"""
    t = after_t(d, card) if which == "after" else max(0, card["start"] - 1)
    out = d / "cards" / f"{card['n']:02d}_{which}_{t}.jpg"
    if not out.exists():
        v = Path(json.loads((d / "progress.json").read_text()).get("video_path") or "")
        for tt in (t, max(0, t - 1), card["start"]):  # 영상 끝과 같은 시각이면 사진이 안 나온다 → 1초 앞
            if v.is_file():
                try:
                    pipeline.grab(v, tt, out)
                except Exception:
                    continue
                if out.exists() and out.stat().st_size:
                    return out
        return d / card["image"]
    return out
