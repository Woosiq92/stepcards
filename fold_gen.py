# 3D 접기 카드: Muse Spark 가 시범 사진을 보고 카드마다 접는 동작을 짧은 형식(접기 프로그램)으로 쓴다.
# 카드 하나씩 쓴다(write_step). 판정은 모델이 아니라 코드와 대조: 브라우저의 fold.js 가 돌려 검사하고(검사기),
# 그 카드의 3D 끝 모양을 시범 영상의 단계 끝 장면과 Muse Spark 가 비교한다(compare). 걸리면 이유를 붙여 그 카드만 다시 쓴다.
import json
import re
from pipeline import client, STEP_MODEL, PRICE_IN, PRICE_OUT, data_url

FORMAT = """Write a fold program: how the cloth or paper changes shape, card by card, so a 3D animation can show each move.

Coordinates: look at the cloth as it lies in the video. The top of the image is the far side, the bottom is the near side.
Points are relative to the CURRENT folded shape's outer bounding box (not the original sheet):
named points top-left, top, top-right, left, center, right, bottom-left, bottom, bottom-right, or [x, y] with 0..1 (x to the right, y toward the viewer).

Moves (ops):
- {"op":"fold","from":P,"to":Q,"dir":"valley"|"mountain","layers":"all"|"top"|N}
  bring point P onto point Q; the crease is halfway between them. valley = the moving part goes over the top (most folds);
  mountain = it goes underneath. layers: "all" folds every layer at P, "top" only the top layer, N the top N layers,
  "bottom" only the bottom layer (to pull out a flap that is hidden underneath, e.g. after turning the cloth over: use "dir":"mountain" so it stays underneath).
  Examples on a flat square: bottom edge up to top edge = {"op":"fold","from":"bottom","to":"top"};
  top-left corner to the middle = {"op":"fold","from":"top-left","to":"center"}.
- {"op":"tuck","from":P,"to":Q} like fold, but the moving part goes under the top layer (into a pocket).
- {"op":"flip","axis":"vertical"|"horizontal"} turn the whole thing over (vertical = left side over to the right).
- {"op":"rotate","deg":90} turn it on the table, clockwise positive.
- {"op":"pinch","axis":"vertical"} gather the middle (for a final bow or butterfly body).
A card that does not change the shape (picking up, smoothing) has "ops": [].
Use at most 4 ops per card; a card is one action, sometimes done on both sides (two ops).

Answer with JSON only:
{"shape":{"w":1,"h":1,"color":"#rrggbb"},"steps":[{"n":1,"ops":[...]}, ...]}
shape: the flat sheet before card 1 (w:h ratio as seen, colour of the cloth)."""

COMPARE = """Each pair below is one step card: first the demonstration photo at the END of that step, then a 3D drawing of the shape our fold program reaches at the end of that step.
Compare only the outline and folds of the cloth: number of corners, which part is folded over which, overall proportions and orientation (the far side of the photo is the top of the drawing).
Ignore colour, hands, shadows, perspective and small size differences. If the cloth is mostly hidden by hands in the photo, answer "unclear".
Answer with JSON only: {"cards":[{"n":1,"match":"yes"|"no"|"unclear","fix":"if no: one short sentence on what the drawing should change"}]}"""


MAX_STILL = 400_000  # 3D 그림 한 장(jpeg data URL) 최대 길이: 480x360 은 보통 30KB 안팎, 이보다 크면 잘못 온 값으로 본다


def _ask(content, effort=None):
    kw = {"reasoning": {"effort": effort}} if effort else {}
    r = client.responses.create(model=STEP_MODEL, input=[{"role": "user", "content": content}], store=False, **kw)
    m = re.search(r"\{.*\}", r.output_text or "", re.S)
    try:
        ans = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        ans = {}
    return ans, r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT


def frame(d, t, last):
    """t초의 1초 사진(f001 = 0초)"""
    i = max(1, min(last, int(round(t)) + 1))
    return d / "frames" / f"f{i:03d}.jpg"


STEP = """Now write only the moves for card n={n}: {sentence}
Before this card the cloth looks like the 3D drawing below (top of the drawing = far side of the video), made by the moves so far:
{prefix}
The first photo is the end of the previous step, the second the end of this step.{shape_q}
Answer with JSON only: {{{shape_a}"ops":[...]}}"""


def write_step(d, cards, n, prefix, current, problems=(), notes=()):
    """카드 하나의 동작만 쓰기(앞 카드까지의 프로그램과 지금 3D 모양 그림을 보고). 첫 카드면 시작 모양(shape)도"""
    last = len(list((d / "frames").glob("f*.jpg")))
    i = next((k for k, c in enumerate(cards) if c["n"] == n), None)
    if i is None:
        return {"ops": None, "cost": 0}
    c, first = cards[i], i == 0
    prev_t = cards[i - 1].get("end", 0) if i else c.get("start", 0)
    content = [{"type": "input_text", "text": FORMAT},
               {"type": "input_text", "text": STEP.format(n=n, sentence=f'{c.get("en", "")} / {c.get("ko", "")}', prefix=json.dumps(prefix, ensure_ascii=False),
                                                         shape_q=" This is the first card: also give the flat starting sheet as \"shape\" (w:h as seen, colour)." if first else "",
                                                         shape_a='"shape":{"w":1,"h":1,"color":"#rrggbb"},' if first else "")},
               {"type": "input_image", "image_url": data_url(frame(d, prev_t, last))},
               {"type": "input_image", "image_url": data_url(frame(d, c.get("end", 0), last))}]
    if isinstance(current, str) and current.startswith("data:image/jpeg;base64,") and len(current) < MAX_STILL:
        content.append({"type": "input_image", "image_url": current})
    if problems or notes:
        content.append({"type": "input_text", "text": "Your last answer for this card had problems:\n- " + "\n- ".join([*problems, *notes]) + "\nFix them."})
    ans, cost = _ask(content, "low")  # 실측(냅킨 2번): 기본 60.6초·low 16.9초 같은 답, minimal 11.3초는 틀림
    ops = ans.get("ops") if isinstance(ans.get("ops"), list) else None
    out = {"ops": ops, "cost": round(cost, 4)}
    if first and isinstance(ans.get("shape"), dict):
        sh = ans["shape"]
        out["shape"] = {"w": float(sh.get("w") or 1), "h": float(sh.get("h") or 1),
                        "color": sh.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(sh.get("color", ""))) else "#c0392b"}
    return out


def compare(d, cards, stills):
    """3D 끝 모양(브라우저가 그린 jpeg)과 시범 끝 장면 비교"""
    last = len(list((d / "frames").glob("f*.jpg")))
    content = [{"type": "input_text", "text": COMPARE}]
    for c in cards:
        s = stills.get(str(c["n"]))
        if not (isinstance(s, str) and s.startswith("data:image/jpeg;base64,") and len(s) < MAX_STILL):
            continue
        content += [{"type": "input_text", "text": f'Card n={c["n"]}: {c.get("en", "")}'},
                    {"type": "input_image", "image_url": data_url(frame(d, c.get("end", 0), last))},
                    {"type": "input_image", "image_url": s}]
    ans, cost = _ask(content, "low")
    out = [{"n": x.get("n"), "match": x.get("match") if x.get("match") in ("yes", "no", "unclear") else "unclear", "fix": str(x.get("fix", ""))[:200]}
           for x in ans.get("cards", []) if isinstance(x, dict)]
    return {"cards": out, "cost": round(cost, 4)}
