# 따라 하기(Coach): 카메라 사진 몇 장을 보고 지금 카드를 넘길지 정한다
# AI는 카드를 넘기거나 다시 보여 주기만 한다. 칭찬·점수·기록 없음, 사진은 저장하지 않음
import json, time
import pipeline

FRAMES = 2  # 최근 사진 수. 4장보다 빠르고 답은 같았음(coach_bench.py)

PROMPT = """A learner is doing a task while watching step cards. The steps are:
{steps}
The learner is now on step {cur}. The images are camera frames from the last few seconds, oldest first.
Look at the latest frames. Answer only JSON: {{"seen": n, "current_done": true/false}}
- "seen": the step number the learner is doing in the latest frame, or 0 if you cannot tell (hands not visible, no action).
- "current_done": true only if step {cur} looks finished."""


def ask(cards, cur, frames):
    steps = "\n".join(f"{i}. {c['en']} (holding: {c.get('object') or '-'})" for i, c in enumerate(cards, 1))
    content = []
    for k, f in enumerate(frames[-FRAMES:]):
        content += [{"type": "input_text", "text": f"frame {k + 1}"}, {"type": "input_image", "image_url": f}]
    content.append({"type": "input_text", "text": PROMPT.format(steps=steps, cur=cur)})
    # 생각 양 최소: 응답 7.8초 → 4.2초, 답은 같았음(coach_bench2.py)
    r = pipeline.client.responses.create(model=pipeline.STEP_MODEL, input=[{"role": "user", "content": content}], store=False,
                                         reasoning={"effort": "minimal"})
    u = r.usage
    cost = u.input_tokens * pipeline.PRICE_IN + u.output_tokens * pipeline.PRICE_OUT
    try:
        d = json.loads(r.output_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```"))
        return int(d.get("seen") or 0), bool(d.get("current_done")), cost
    except (ValueError, TypeError, AttributeError):
        return 0, False, cost


def in_hand(frame, card):
    """SAM: 이 카드의 물건이 손과 겹치는가. 물건 이름이 없으면 None(판단 안 함)."""
    if not card.get("object"):
        return None
    box, _, touch = pipeline.find_box(frame, card)
    return bool(box and touch)


def check(cards, cur, frames, prev_seen=0):
    """cur는 1부터. decision: next(다음 카드), again(뒤 단계가 처음 보임 → 지금 카드 다시 보여 주기),
    jump(뒤 단계가 두 번 연속 보임 → 그 카드로 따라감, target), wait(기다림).
    prev_seen은 바로 앞 판단의 seen(사람이 직접 넘기면 0으로)."""
    t0 = time.time()
    seen, done, cost = ask(cards, cur, frames)
    decision, sam, target = "wait", None, None
    if cur < len(cards) and (seen == cur + 1 or (done and seen in (0, cur))):
        # Muse Spark가 넘기자고 하면 SAM으로 한 번 더 본다: 다음 물건을 들었거나, 지금 물건을 내려놓았으면 동의
        nxt, now = in_hand(frames[-1], cards[cur]), in_hand(frames[-1], cards[cur - 1])
        sam = {"next_in_hand": nxt, "current_in_hand": now}
        cost += 0.0025 * (2 * ((nxt is not None) + (now is not None)))  # SAM $2.5/1000장, 손+물건 최소 2번씩
        decision = "next" if (nxt is not False or now is False) else "wait"
    elif seen > cur + 1:
        decision, target = ("jump", seen) if prev_seen > cur + 1 else ("again", None)
    return {"decision": decision, "target": target, "seen": seen, "current_done": done, "sam": sam,
            "latency": round(time.time() - t0, 2), "cost": round(cost, 4)}
