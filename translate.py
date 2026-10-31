# 상대 언어로 카드 보기: 보호자·동료가 읽는 언어로 카드 문장을 옮긴다.
# 만든 사람은 그 언어를 못 읽을 수 있으니, 원문을 보지 않은 두 번째 호출이 번역만 보고 한국어·영어로 되옮긴다.
# 숫자가 빠졌는지는 코드가 본다. 만든 사람이 되옮긴 문장을 보고 '확인'해야 학습자 화면에 나온다(저장은 app.py).
import json
import re
from pipeline import client, STEP_MODEL, PRICE_IN, PRICE_OUT

TRANSLATE = """Translate these picture step cards into {language} for a parent or coworker who reads {language}.
Each card is one action. Keep it a short, plain instruction in everyday words, the same single action,
and keep every amount, number, direction and side (up, left, 18 g ...).

Cards (Korean | English):
{cards}

Answer with JSON only: {{"name":"the language's own name in that language","cards":[{{"n":1,"x":"..."}}]}}"""

BACK = """These are instructions from picture step cards. Translate each one into Korean and into English, literally,
so someone can check what it says. Do not improve or fix them.

{cards}

Answer with JSON only: {{"cards":[{{"n":1,"ko":"...","en":"..."}}]}}"""

NUM = re.compile(r"\d+(?:[.,/]\d+)?")


def _ask(prompt):
    r = client.responses.create(model=STEP_MODEL, input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}], store=False)
    m = re.search(r"\{.*\}", r.output_text or "", re.S)
    try:
        ans = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        ans = {}
    return ans, r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT


def problems(cards, out):
    """코드 검사: 빠진 카드, 빈 문장, 원문 숫자가 번역에 없는 카드"""
    by, found = {c["n"]: c for c in out}, []
    for i, c in enumerate(cards):
        x = by.get(c["n"], {}).get("x", "")
        if not x:
            found.append({"n": c["n"], "card": i + 1, "what": "missing"})
        elif missing := [d for d in NUM.findall(c.get("ko", "") + " " + c.get("en", "")) if d not in x]:
            found.append({"n": c["n"], "card": i + 1, "what": "number", "detail": sorted(set(missing))})
    return found


def run(cards, language):
    listing = "\n".join(f'{c["n"]}. {c.get("ko", "")} | {c.get("en", "")}' for c in cards)
    ans, cost = _ask(TRANSLATE.format(language=language, cards=listing))
    ns = {c["n"] for c in cards}
    out = [{"n": c["n"], "x": c["x"].strip()} for c in ans.get("cards", [])
           if isinstance(c, dict) and c.get("n") in ns and isinstance(c.get("x"), str) and c["x"].strip()]
    if out:  # 되옮기기: 원문을 보여 주지 않는다(보여 주면 원문을 베껴 와서 확인이 안 된다)
        back, c2 = _ask(BACK.format(cards="\n".join(f'{c["n"]}. {c["x"]}' for c in out)))
        cost += c2
        bb = {b.get("n"): b for b in back.get("cards", []) if isinstance(b, dict)}
        for c in out:
            b = bb.get(c["n"], {})
            c["xb"] = {k: str(b.get(k, "")).strip()[:200] for k in ("ko", "en")}
    return {"name": str(ans.get("name", "")).strip()[:40] or language, "cards": out,
            "problems": problems(cards, out), "cost": round(cost, 4)}
