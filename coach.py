# 따라 하기(Coach): 카메라 사진 몇 장을 보고 지금 카드를 넘길지 정한다
# AI는 카드를 넘기거나 다시 보여 주기만 한다. 칭찬·점수·기록 없음, 사진은 저장하지 않음
import json, os, re, threading, time
from openai import OpenAI
import pipeline

FRAMES = int(os.environ.get("COACH_FRAMES") or 2)  # 최근 사진 수. 4장보다 빠르고 답은 같았음(coach_bench.py). 환경 변수는 측정용
# 이 맥에서 돌리는 공개 가중치 Muse Glimmer(llama-server). 사진이 맥 밖으로 나가지 않는다
LOCAL_URL = os.environ.get("GLIMMER_URL", "http://127.0.0.1:8791/v1")
local_client = OpenAI(base_url=LOCAL_URL, api_key="local", timeout=60)


def local_ready():
    try:
        local_client.models.list()
        return True
    except Exception:
        return False


REF_PROMPT = """
The last image (REFERENCE) shows how step {cur} looks when it is done correctly. Compare the latest frame with it and also report:
"state": "done" (step {cur} result matches the reference), "not_yet" (still in progress), "different" (done in a way that clearly differs from the reference: wrong side, amount or place), or "unclear";
"hint_ko"/"hint_en": only if "different", ONE short instruction (Korean ending in ~세요, at most 20 characters), else "".
Then the JSON is: {{"seen": n, "current_done": true/false, "state": "...", "hint_ko": "...", "hint_en": "..."}}"""


def extras(text):
    """실시간 확인 답(state·hint)을 읽는다. 없으면 빈 dict"""
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    return {k: d[k] for k in ("state", "hint_ko", "hint_en") if k in d}


def ask_local(cards, cur, frames, ref=None):
    """Glimmer는 생각부터 길게 써서 18초 넘게 걸렸다 → 답의 첫머리를 채워 생각을 건너뛴다(4.3초, 16장 중 13~15장 맞음)"""
    steps = "\n".join(f"{i}. {c['en']} (holding: {c.get('object') or '-'})" for i, c in enumerate(cards, 1))
    content = []
    for k, f in enumerate(frames[-FRAMES:]):
        content += [{"type": "text", "text": f"frame {k + 1}"}, {"type": "image_url", "image_url": {"url": f}}]
    if ref:
        content += [{"type": "text", "text": "REFERENCE"}, {"type": "image_url", "image_url": {"url": ref}}]
    content.append({"type": "text", "text": PROMPT.format(steps=steps, cur=cur) + (REF_PROMPT.format(cur=cur) if ref else "")})
    head = '{"seen": '
    r = local_client.chat.completions.create(model="glimmer", max_tokens=140 if ref else 80, temperature=0,
                                             messages=[{"role": "user", "content": content}, {"role": "assistant", "content": head}])
    out = head + (r.choices[0].message.content or "")
    seen, done = re.search(r'"seen"\s*:\s*(\d+)', out), re.search(r'"current_done"\s*:\s*(true|false)', out)
    iv = re.search(r'"in_view"\s*:\s*(true|false)', out)
    need = {k: (m.group(1) if (m := re.search(rf'"{k}"\s*:\s*"([^"]*)"', out)) else "") for k in ("need_ko", "need_en")}
    return int(seen.group(1)) if seen else 0, bool(done and done.group(1) == "true"), 0.0, extras(out) if ref else {}, view({"in_view": (iv.group(1) == "true") if iv else None, **need})

PROMPT = """A learner is doing a task while watching step cards. The steps are:
{steps}
The learner is now on step {cur}. The images are camera frames from the last few seconds, oldest first.
Look at the latest frames. Answer only JSON: {{"seen": n, "current_done": true/false, "in_view": true/false, "need_ko": "", "need_en": ""}}
- "seen": the step number the learner is doing in the latest frame, or 0 if you cannot tell (hands not visible, no action).
- "current_done": true only if step {cur} looks finished.
- "in_view": true if everything needed to judge step {cur} is clearly inside the latest frame (for a hand task the hands and the object; for helping someone into a car the whole person, the helper and the car door; for signing the upper body, both hands and the face); false if part of it is out of view, cut off at the edge, too far away or blurred.
- "need_ko", "need_en": only when in_view is false, what must come into view for step {cur}, as a short noun phrase in Korean and in English (e.g. "냅킨과 두 손" / "the napkin and both hands"); otherwise empty."""


def view(d):
    """화면에 보여야 할 것: in_view(모르면 None)와, 안 보일 때 무엇을 보이게 할지(짧은 말, 한국어·영어)"""
    iv = d.get("in_view") if isinstance(d.get("in_view"), bool) else None
    out = {"in_view": iv, **{k: (str(d.get(k) or "").strip()[:40] if iv is False else "") for k in ("need_ko", "need_en")}}
    return {**out, **{k: str(d.get(k) or "").strip()[:60] for k in ("saw_ko", "saw_en")}}  # 지금 카메라에 보이는 것: 학습자가 무엇이 진행 중인지 알게(11-03 실사용 요청)


def ask(cards, cur, frames, ref=None):
    steps = "\n".join(f"{i}. {c['en']} (holding: {c.get('object') or '-'})" for i, c in enumerate(cards, 1))
    content = []
    for k, f in enumerate(frames[-FRAMES:]):
        content += [{"type": "input_text", "text": f"frame {k + 1}"}, {"type": "input_image", "image_url": f}]
    if ref:  # 실시간 확인: 지금 카드의 완료 기준 사진을 같이 본다(같은 판단 한 번으로)
        content += [{"type": "input_text", "text": "REFERENCE"}, {"type": "input_image", "image_url": ref}]
    content.append({"type": "input_text", "text": PROMPT.format(steps=steps, cur=cur) + (REF_PROMPT.format(cur=cur) if ref else "")})
    # 생각 양 최소: 응답 7.8초 → 4.2초, 답은 같았음(coach_bench2.py)
    r = pipeline.client.responses.create(model=pipeline.STEP_MODEL, input=[{"role": "user", "content": content}], store=False,
                                         reasoning={"effort": "minimal"}, timeout=30)  # 판단은 보통 2~3초: 멈춘 요청이 서버 일꾼을 최대 15분 붙잡지 않게
    u = r.usage
    cost = u.input_tokens * pipeline.PRICE_IN + u.output_tokens * pipeline.PRICE_OUT
    try:
        d = json.loads(r.output_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        return int(d.get("seen") or 0), bool(d.get("current_done")), cost, extras(r.output_text) if ref else {}, view(d)
    except (ValueError, TypeError, AttributeError):
        return 0, False, cost, {}


STATE_PROMPT = """A learner is copying a demonstration, step by step. The steps are:
{steps}
The learner is now on step {cur}. The first images are camera frames from the last second, oldest first.
After them come REFERENCE photos from the demonstration video, each showing how the work looks at one moment:
{refs}
Compare the work in the LATEST camera frame with the references: shape, which parts are folded or placed where, how much is done.
Ignore the camera angle, distance, lighting, background, colour shade and the hands themselves; small differences in neatness are fine.
The learner may use a similar stand-in (paper for a napkin, another cup or towel): judge the shape and state of the work, not whether it is the same object.
For a whole-body step (dance, exercise), the camera may cut off the legs or feet in a small room: if the visible body (arms, posture, upper-body movement) is enough to tell the step, still answer match and set in_view true; set in_view false only when the step cannot be told from what is visible.
Answer only JSON: {{"match": k, "seen": n, "in_view": true/false, "need_ko": "", "need_en": "", "saw_ko": "", "saw_en": ""{live_keys}}}
- "match": the letter-number k of the reference the latest frame looks most like (0, 1, 2 ...), or -1 if the work is hidden or not in view.
  If the learner is in the middle of a step, answer the reference it still looks like (the one before the change).
- "seen": the step number the learner is doing in the latest frame, or 0 if you cannot tell.
- "in_view": true if the work (or its stand-in) needed to judge step {cur} is clearly inside the latest frame, even if held in one hand or up to the camera; false if cut off, too far, or blurred.
- "need_ko", "need_en": only when in_view is false, what must come into view, as a short noun phrase in Korean and in English (e.g. "냅킨과 두 손" / "the napkin and both hands"); otherwise empty.
- "saw_ko", "saw_en": what the latest frame shows about the work, in plain words, Korean ending in ~요 (at most 25 characters) and English (at most 8 words), e.g. "흰 종이를 펼쳐 들고 있어요" / "holding up a flat sheet of paper"."""

STATE_LIVE = """
- "state": "done" if the latest frame matches reference 1 (step {cur} done right), "not_yet" if the work still looks like reference 0,
  "different" if step {cur} looks finished but clearly differs from reference 1 (wrong side, amount or place), else "unclear".
- "hint_ko"/"hint_en": only if "different", ONE short instruction (Korean ending in ~세요, at most 20 characters), else ""."""


def ask_states(cards, cur, frames, refs, live=False):
    """단계 끝 사진들과 맞추기. refs = [(설명, 사진 url)], 0 = 지금 단계 시작 모습, 1 = 지금 단계 끝, 2 = 다음 단계 끝 ...
    돌려줌: (match, seen, cost, live 답, view)"""
    steps = "\n".join(f"{i}. {c['en']}" for i, c in enumerate(cards, 1))
    content = []
    for k, f in enumerate(frames[-FRAMES:]):
        content += [{"type": "input_text", "text": f"camera frame {k + 1}"}, {"type": "input_image", "image_url": f}]
    for k, (label, url) in enumerate(refs):
        content += [{"type": "input_text", "text": f"REFERENCE {k}: {label}"}, {"type": "input_image", "image_url": url}]
    text = STATE_PROMPT.format(steps=steps, cur=cur, refs="\n".join(f"{k}. {label}" for k, (label, _) in enumerate(refs)),
                               live_keys=', "state": "", "hint_ko": "", "hint_en": ""' if live else "")
    content.append({"type": "input_text", "text": text + (STATE_LIVE.format(cur=cur) if live else "")})
    r = pipeline.client.responses.create(model=pipeline.STEP_MODEL, input=[{"role": "user", "content": content}], store=False,
                                         reasoning={"effort": "minimal"}, timeout=30)  # 판단은 보통 2~3초: 멈춘 요청이 서버 일꾼을 최대 15분 붙잡지 않게
    u = r.usage
    cost = u.input_tokens * pipeline.PRICE_IN + u.output_tokens * pipeline.PRICE_OUT
    m = re.search(r"\{.*\}", r.output_text or "", re.S)
    try:
        d = json.loads(m.group(0)) if m else {}
    except ValueError:
        d = {}
    try:
        match = int(d.get("match", -1))
    except (TypeError, ValueError):
        match = -1
    if not -1 <= match < len(refs):  # 보여 준 사진에 없는 번호: 확인 규칙을 건너뛰고 맨 끝 카드로 건너뛸 수 있었다(11-02 검토)
        match = -1
    try:
        seen = int(d.get("seen") or 0)
    except (TypeError, ValueError):
        seen = 0
    return match, seen, cost, extras(r.output_text) if live else {}, view(d)


def in_hand(frame, card):
    """SAM: 이 카드의 물건이 손과 겹치는가. 물건 이름이 없으면 None(판단 안 함)."""
    if not card.get("object"):
        return None
    box, _, touch = pipeline.find_box(frame, card)
    return bool(box and touch)


def check(cards, cur, frames, prev_seen=0, local=False, ref=None, refs=None, prev_match=-1, similar=False, on_card=None):
    """cur는 1부터. decision: next(다음 카드), finished(마지막 카드를 마침 → 화면에서 두 번 연속일 때 끝 화면), again(뒤 단계가 처음 보임 → 지금 카드 다시 보여 주기),
    jump(뒤 단계가 두 번 연속 보임 → 그 카드로 따라감, target), wait(기다림).
    prev_seen은 바로 앞 판단의 seen(사람이 직접 넘기면 0으로).
    local이면 Glimmer만 쓴다. SAM은 Meta API라 사진이 밖으로 나가므로 확인 없이 Glimmer 판단대로 넘긴다."""
    t0 = time.time()
    if refs and not local:
        return check_states(cards, cur, frames, refs, live=ref is not None, t0=t0, prev_match=prev_match, similar=similar, on_card=on_card)
    res = (ask_local if local else ask)(cards, cur, frames, ref) if ref else (ask_local if local else ask)(cards, cur, frames)
    seen, done, cost = res[:3]
    seen_view = res[4] if len(res) > 4 else view({})  # 이 카드를 판단할 것이 화면 안에 다 보이는가(안 보이면 화면이 무엇을 보이게 할지 알려 준다)
    live = live_state(res[3] if len(res) > 3 else {}, cards[cur - 1]) if ref else None
    if live and live["state"] == "done":  # 기준 사진과 같은 결과면 '지금 단계 마침'으로 본다
        done = True
    if not 0 <= seen <= len(cards):  # 없는 단계 번호는 못 본 것으로
        seen = 0
    decision, sam, target = "wait", None, None
    if local and cur < len(cards) and (seen == cur + 1 or (done and seen in (0, cur))):
        decision = "next"
    elif cur < len(cards) and (seen == cur + 1 or (done and seen in (0, cur))):
        # Muse Spark가 넘기자고 하면 SAM으로 한 번 더 본다: 다음 물건을 들었거나, 지금 물건을 내려놓았으면 동의
        nxt, now = in_hand(frames[-1], cards[cur]), in_hand(frames[-1], cards[cur - 1])
        sam = {"next_in_hand": nxt, "current_in_hand": now}
        cost += 0.0025 * (2 * ((nxt is not None) + (now is not None)))  # SAM $2.5/1000장, 손+물건 최소 2번씩
        decision = "next" if (nxt is not False or now is False) else "wait"
    elif cur == len(cards) and done and seen in (0, cur):
        decision = "finished"
    elif seen > cur + 1:
        decision, target = ("jump", seen) if prev_seen == seen else ("again", None)
    return {"decision": decision, "target": target, "seen": seen, "current_done": done, "sam": sam,
            "latency": round(time.time() - t0, 2), "cost": round(cost, 4), "local": local, **seen_view, **(live or {})}


AHEAD = int(os.environ.get("COACH_AHEAD") or 2)  # 지금 단계 끝 다음으로 몇 단계 끝까지 보여 줄지(빨리 한 학습자도 따라잡게). 환경 변수는 측정용


def state_refs(d, cards, cur):
    """맞출 사진: 0 = 지금 단계 시작 모습(앞 단계 끝, 1번이면 시작 전), 1 = 지금 단계 끝, 2.. = 그다음 단계들 끝. 사진은 영상에서 한 번 뽑아 둔다"""
    import verify  # verify 가 coach 를 불러와서 여기서
    i = cur - 1
    refs = [(f"start of step {cur} (before it)", verify.reference(d, cards[0], "before")) if i == 0 else
            (f"after step {cur - 1} = start of step {cur}", verify.reference(d, cards[i - 1], "after"))]
    for k in range(i, min(len(cards), i + 1 + AHEAD)):
        refs.append((f"after step {k + 1}", verify.reference(d, cards[k], "after")))
    return [(label, pipeline.data_url(small(path))) for label, path in refs]


def small(path, w=480):
    """판단에 넣는 시범 사진은 카메라 사진과 같은 480px 로(원본 1280px 네 장이 느린 판단 8~17초의 원인 후보). 한 번 만들어 둔다"""
    from PIL import Image
    out = path.with_name(f"{path.stem}_w{w}.jpg")
    if not (out.exists() and out.stat().st_size):
        im = Image.open(path).convert("RGB")
        im.thumbnail((w, w * 2))
        tmp = out.with_name(f".{os.getpid()}_{threading.get_ident()}_{out.name}")  # 반쯤 쓴 사진이 남지 않게 바꿔 끼운다
        im.save(tmp, "JPEG", quality=75)
        os.replace(tmp, out)
    return out


CONFIRM_ALL = os.environ.get("COACH_CONFIRM") == "all"  # 측정용: 모든 넘김을 두 번 연속 확인
MIN_DWELL = 0.5  # 카드가 뜬 뒤 시범 단계 시간의 이 비율이 지나기 전엔 한 장 넘김을 안 한다: 뿌리기처럼 조금씩 쌓이는 단계는 조금만 해도 끝 사진과 닮아 6~15초 일찍 넘겼다(라떼 두 판 같은 곳)
SIMILAR = 14  # 단계 앞뒤 시범 사진의 차이(48x36 흑백 평균 밝기 차)가 이보다 작으면 두 번 연속 '끝'일 때만 넘긴다. 냅킨 뒤집기 11.6: 한 번만 보고 6초 일찍 넘겼다
_change = {}


def change(d, cards, cur):
    """지금 단계 앞(0)과 끝(1) 시범 사진이 얼마나 다른가. 뒤집기처럼 거의 같으면 한 번 본 것으로 넘기지 않는다"""
    from PIL import Image, ImageChops, ImageStat
    import verify
    i = cur - 1
    a = verify.reference(d, cards[0], "before") if i == 0 else verify.reference(d, cards[i - 1], "after")
    b = verify.reference(d, cards[i], "after")
    key = (str(a), str(b))
    if key not in _change:
        sm = lambda p: Image.open(p).convert("L").resize((48, 36))
        _change[key] = ImageStat.Stat(ImageChops.difference(sm(a), sm(b))).mean[0]
    return _change[key]


def check_states(cards, cur, frames, refs, live, t0, prev_match=-1, similar=False, on_card=None):
    """시범의 단계 끝 사진과 맞춰서 넘긴다(11-02: 문장만 보고 단계를 가리게 하면 7번 단계부터 50초 넘게 못 넘겼다).
    지금 단계 끝(1) 이후 사진과 같으면 next, 마지막 카드면 finished. 0 이면 wait.
    SAM 확인은 뺐다: 넘기는 판단마다 3~9초를 더했고, 기록된 13번 중 한 번도 넘김을 막지 않았다"""
    match, seen, cost, lv, seen_view = ask_states(cards, cur, frames, refs, live)
    if not 0 <= seen <= len(cards):
        seen = 0
    # 판단은 '몇 번 단계까지 끝난 모습인가'(절대 번호)로 주고받는다: 카드가 넘어가도 앞 판단이 그대로 뜻이 있다
    # (상대값으로 두고 넘길 때 지웠더니, 앞서 간 학습자를 두 번 연속 확인하지 못해 냅킨에서 30초 넘게 뒤처졌다)
    done_step = cur + match - 1 if match >= 0 else -1
    confirm = similar or CONFIRM_ALL
    c = cards[cur - 1]
    soon = on_card is not None and on_card < MIN_DWELL * max(0, (c.get("end") or 0) - (c.get("start") or 0))  # 시범 시간의 절반도 안 지났다
    done = done_step > cur or (done_step == cur and not soon and (not confirm or prev_match >= cur))  # 앞뒤가 비슷한 단계는 바로 앞 판단도 '끝'이었을 때만
    # 몇 단계 앞선 모습이 두 번 연속이면 그 카드로 바로(한 번만으로 건너뛰면 수건에서 3번 중 2번 너무 앞섰다). 한 번이면 한 장만
    target = min(len(cards), min(done_step, prev_match) + 1) if done_step > cur and prev_match > cur else None
    decision = "finished" if done and cur == len(cards) else "jump" if target and target > cur + 1 else "next" if done else "wait"
    live_out = live_state(lv, cards[cur - 1]) if live else None
    return {"decision": decision, "target": target if decision == "jump" else None, "seen": seen, "current_done": done, "match": match, "done_step": done_step, "sam": None,
            "latency": round(time.time() - t0, 2), "cost": round(cost, 4), "local": False, **seen_view, **(live_out or {})}


def live_state(x, card):
    """실시간 확인 답을 화면용으로: 모르는 값은 unclear, 안내 길이·빈칸은 확인하기와 같은 규칙(verify.tidy)"""
    import verify  # verify 가 coach 를 불러와서 여기서
    t = verify.tidy({"result": x.get("state"), "confidence": 1, "hint_ko": x.get("hint_ko"), "hint_en": x.get("hint_en")}, card)
    return {"state": t["result"], "hint_ko": t["hint_ko"], "hint_en": t["hint_en"]}
