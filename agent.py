# 교사 지시 에이전트: "글을 잘 못 읽는 학생용으로 더 쉽게" 같은 부탁을 받아 Muse Spark가 카드 문장을 고칠 안을 만든다.
# 모델은 check_cards 도구로 코드 검사기를 직접 돌려 보고, 걸리면 고쳐서 다시 확인한다. 최종 판정도 코드가 한다.
# 저장하지 않는다: 교사가 화면에서 '적용'을 눌러야 바뀐다.
import json
import re
from check import check
from pipeline import client, STEP_MODEL, PRICE_IN, PRICE_OUT

MAX_CHECKS = 4
CHANGE = {"type": "object", "additionalProperties": False, "required": ["n", "ko", "en"],
          "properties": {"n": {"type": "integer"}, "ko": {"type": "string"}, "en": {"type": "string"}}}
TOOL = {"type": "function", "name": "check_cards",
        "description": "Run the code-only rule checker on all cards with your proposed sentence changes applied. "
                       "Returns the problems it finds; fix them and check again before answering.",
        "parameters": {"type": "object", "additionalProperties": False, "required": ["changes"],
                       "properties": {"changes": {"type": "array", "items": CHANGE}}}}
PROMPT = """You help a special-education teacher revise picture step cards (task analysis) for learners with intellectual disabilities.
Each card is one action with a Korean sentence (ko) and an English sentence (en).

Teacher's request: {instruction}

Cards:
{cards}

Rules:
- Change only the sentences (ko and en). Do not add, remove, merge or reorder cards; say so in the note if the request needs that.
- One action per card. Korean sentences are plain polite instructions ending in '~세요', at most 25 characters.
- Keep amounts and object names that are already there unless the teacher asks otherwise.
- Keep natural, grammatical Korean with its particles (을/를, 에). "Simpler" means more common words or fewer ideas, not dropping particles. If a sentence is already simple, leave it out.
- Never drop words for direction, side, place or amount (위로, 아래로, 오른쪽, 18g ...): the learner needs them to do the step.
- Include only the cards you change.
Before answering, call check_cards with your changes and fix anything it reports.
Answer with JSON only: {{"changes":[{{"n":1,"ko":"...","en":"..."}}],"note":"one short Korean sentence saying what you changed"}}"""


def apply(cards, changes):
    by = {c.get("n"): c for c in changes if isinstance(c, dict)}
    return [{**c, **{k: by[c["n"]][k] for k in ("ko", "en") if isinstance(by.get(c["n"], {}).get(k), str)}} for c in cards]


def run(cards, duration, instruction):
    listing = "\n".join(f'{c["n"]}. ko: {c.get("ko", "")} | en: {c.get("en", "")} | in hand: {c.get("object", "")}' for c in cards)
    messages = [{"role": "user", "content": [{"type": "input_text", "text": PROMPT.format(instruction=instruction, cards=listing)}]}]
    cost, checks = 0.0, 0
    for _ in range(MAX_CHECKS + 3):  # Meta API는 tool_choice "auto"만 받아서, 한도를 넘으면 도구 대신 "지금 답하라"를 돌려준다
        r = client.responses.create(model=STEP_MODEL, input=messages, store=False, tools=[TOOL])
        cost += r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT
        fcs = [o for o in r.output if o.type == "function_call"]
        if not fcs:
            break
        messages += [o.model_dump(exclude_none=True) for o in r.output if o.type in ("function_call", "reasoning")]
        for fc in fcs:
            if checks >= MAX_CHECKS:
                out = "No more checks are available. Answer now with the JSON only."
            else:
                checks += 1
                proposed = json.loads(fc.arguments or "{}").get("changes", [])
                problems, _ = check(apply(cards, proposed), duration)
                out = json.dumps({"ok": not problems, "problems": problems}, ensure_ascii=False)
            messages.append({"type": "function_call_output", "call_id": fc.call_id, "output": out})
    m = re.search(r"\{.*\}", r.output_text or "", re.S)
    try:
        ans = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        ans = {}
    old = {c["n"]: c for c in cards}
    changes = [{"n": c["n"], "ko": c["ko"].strip(), "en": c["en"].strip(), "ko_before": old[c["n"]].get("ko", ""), "en_before": old[c["n"]].get("en", "")}
               for c in ans.get("changes", []) if isinstance(c, dict) and c.get("n") in old
               and isinstance(c.get("ko"), str) and isinstance(c.get("en"), str)
               and (c["ko"].strip(), c["en"].strip()) != (old[c["n"]].get("ko", ""), old[c["n"]].get("en", ""))]
    problems, _ = check(apply(cards, changes), duration)  # 최종 판정은 모델이 아니라 코드
    return {"changes": changes, "note": str(ans.get("note", ""))[:200], "problems": problems, "checks": checks, "cost": round(cost, 4)}
