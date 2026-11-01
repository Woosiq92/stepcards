# 3D 접기 카드: Muse Spark 가 시범 사진을 보고 카드마다 접는 동작을 짧은 형식(접기 프로그램)으로 쓴다.
# 판정은 모델이 아니라 코드와 대조: 브라우저의 fold.js 가 프로그램을 돌려 검사하고(검사기),
# 3D 끝 모양을 시범 영상의 단계 끝 장면과 Muse Spark 가 비교한다(compare). 둘 다 걸리면 이유를 붙여 다시 쓴다.
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


def _ask(content):
    r = client.responses.create(model=STEP_MODEL, input=[{"role": "user", "content": content}], store=False)
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


def write(d, cards, previous=None, problems=(), notes=()):
    """접기 프로그램 쓰기. previous 와 problems(검사기)·notes(대조)가 있으면 그 부분만 고쳐 쓴다"""
    last = len(list((d / "frames").glob("f*.jpg")))
    content = [{"type": "input_text", "text": FORMAT},
               {"type": "input_text", "text": "Before card 1 (the starting sheet):"},
               {"type": "input_image", "image_url": data_url(frame(d, cards[0].get("start", 0), last))}]
    for c in cards:
        content += [{"type": "input_text", "text": f'Card n={c["n"]} ({c.get("start")}-{c.get("end")} s): {c.get("en", "")} / {c.get("ko", "")}. Photo at the end of this step:'},
                    {"type": "input_image", "image_url": data_url(frame(d, c.get("end", 0), last))}]
    if previous:
        content.append({"type": "input_text", "text": "Your previous program:\n" + json.dumps(previous, ensure_ascii=False)
                        + ("\nThe code checker found these problems:\n- " + "\n- ".join(problems) if problems else "")
                        + ("\nComparing the 3D result with the photos found these differences:\n- " + "\n- ".join(notes) if notes else "")
                        + "\nFix those cards and answer with the whole program again."})
    ans, cost = _ask(content)
    prog = ans if isinstance(ans.get("steps"), list) else None
    if prog:  # 모양 값 정리(색은 #rrggbb 만)
        sh = prog.get("shape") if isinstance(prog.get("shape"), dict) else {}
        prog["shape"] = {"w": float(sh.get("w") or 1), "h": float(sh.get("h") or 1),
                         "color": sh.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(sh.get("color", ""))) else "#c0392b"}
    return {"program": prog, "cost": round(cost, 4)}


def compare(d, cards, stills):
    """3D 끝 모양(브라우저가 그린 jpeg)과 시범 끝 장면 비교"""
    last = len(list((d / "frames").glob("f*.jpg")))
    content = [{"type": "input_text", "text": COMPARE}]
    for c in cards:
        s = stills.get(str(c["n"]))
        if not (isinstance(s, str) and s.startswith("data:image/jpeg;base64,") and len(s) < 400_000):
            continue
        content += [{"type": "input_text", "text": f'Card n={c["n"]}: {c.get("en", "")}'},
                    {"type": "input_image", "image_url": data_url(frame(d, c.get("end", 0), last))},
                    {"type": "input_image", "image_url": s}]
    ans, cost = _ask(content)
    out = [{"n": x.get("n"), "match": x.get("match") if x.get("match") in ("yes", "no", "unclear") else "unclear", "fix": str(x.get("fix", ""))[:200]}
           for x in ans.get("cards", []) if isinstance(x, dict)]
    return {"cards": out, "cost": round(cost, 4)}
