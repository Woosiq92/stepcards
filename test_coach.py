import pytest
import coach

CARDS = [{"en": f"step {i}", "object": "cup"} for i in range(1, 10)]


def run(monkeypatch, seen, cur, prev_seen=0, done=False):
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (seen, done, 0.0))
    monkeypatch.setattr(coach, "in_hand", lambda f, c: True)
    return coach.check(CARDS, cur, ["f"], prev_seen)


def test_out_of_range_seen_never_jumps(monkeypatch):
    r = run(monkeypatch, 12, 2, prev_seen=12)
    assert r["decision"] == "wait" and r["target"] is None and r["seen"] == 0


def test_different_later_steps_again(monkeypatch):
    assert run(monkeypatch, 4, 2)["decision"] == "again"
    r = run(monkeypatch, 6, 2, prev_seen=4)
    assert r["decision"] == "again" and r["target"] is None


def test_same_later_step_twice_jumps(monkeypatch):
    r = run(monkeypatch, 6, 2, prev_seen=6)
    assert r["decision"] == "jump" and r["target"] == 6


def test_next_unchanged(monkeypatch):
    r = run(monkeypatch, 3, 2)
    assert r["decision"] == "next" and r["sam"] == {"next_in_hand": True, "current_in_hand": True}
    assert run(monkeypatch, 0, 2, done=True)["decision"] == "next"
    assert run(monkeypatch, 0, 2)["decision"] == "wait"


def test_last_card_done_finishes(monkeypatch):
    assert run(monkeypatch, 9, 9, done=True)["decision"] == "finished"
    assert run(monkeypatch, 0, 9, done=True)["decision"] == "finished"
    assert run(monkeypatch, 9, 9, done=False)["decision"] == "wait"
    assert run(monkeypatch, 8, 8, done=True)["decision"] != "finished"


# 실시간 확인: 기준 사진을 주면 state·hint 가 붙고, done 이면 넘기기, 이상한 값은 unclear
def test_live_state(monkeypatch):
    monkeypatch.setattr(coach, "in_hand", lambda f, c: True)
    CARDS2 = [{"en": f"step {i}", "ko": f"{i}단계를 하세요.", "object": "cup"} for i in range(1, 10)]
    monkeypatch.setattr(coach, "ask", lambda c, n, f, ref=None: (2, False, 0.0, {"state": "different", "hint_ko": "끝까지 접으세요.", "hint_en": "Fold all the way."}))
    r = coach.check(CARDS2, 2, ["f"], 0, False, "data:ref")
    assert r["state"] == "different" and r["hint_ko"] == "끝까지 접으세요." and r["decision"] == "wait"
    monkeypatch.setattr(coach, "ask", lambda c, n, f, ref=None: (2, False, 0.0, {"state": "done"}))
    assert coach.check(CARDS2, 2, ["f"], 0, False, "data:ref")["decision"] == "next"
    monkeypatch.setattr(coach, "ask", lambda c, n, f, ref=None: (2, False, 0.0, {"state": "???"}))
    assert coach.check(CARDS2, 2, ["f"], 0, False, "data:ref")["state"] == "unclear"
    assert "state" not in run(monkeypatch, 3, 2)   # 기준 사진이 없으면 예전과 같다


def test_in_view_and_what_to_show(monkeypatch):
    # 카드마다 보여야 할 것이 다르다: 안 보이면 무엇을 보이게 할지(짧은 말)를 넘긴다. 모르면 None(옛 답 형식도 그대로 된다)
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (0, False, 0.0, {}, coach.view({"in_view": False, "need_ko": "차 문과 휠체어에 앉은 사람", "need_en": "the car door and the seated person"})))
    r = coach.check(CARDS, 2, ["f"])
    assert r["in_view"] is False and r["need_ko"] == "차 문과 휠체어에 앉은 사람"
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (0, False, 0.0, {}, coach.view({"in_view": True, "need_ko": "x"})))
    assert coach.check(CARDS, 2, ["f"])["need_ko"] == ""  # 보이면 안내 말 없음
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (0, False, 0.0))
    assert coach.check(CARDS, 2, ["f"])["in_view"] is None


# 11-02 시범의 단계 끝 사진과 맞추기(Meta API 경로)
def states(monkeypatch, match, cur, prev_match=-1, similar=False, seen=0):
    monkeypatch.setattr(coach, "ask_states", lambda c, n, f, r, live=False, action=False: (match, seen, 0.0, {}, coach.view({})))
    return coach.check(CARDS, cur, ["f"], 0, False, None, [("a", "u")], prev_match, similar)


def test_states_match_after_step_moves_on(monkeypatch):
    assert states(monkeypatch, 1, 2)["decision"] == "next"
    assert states(monkeypatch, 2, 2)["decision"] == "next"  # 앞선 모습 한 번은 한 장만
    r = states(monkeypatch, 3, 2, prev_match=3)  # 지금: 4번까지 끝난 모습, 앞 판단: 3번까지
    assert r["decision"] == "jump" and r["target"] == 4  # 두 번 연속이면 둘 중 작은 쪽 다음 카드로
    assert states(monkeypatch, 1, 3, prev_match=3)["decision"] == "next"  # 넘긴 뒤에도 앞 판단(3번 끝)이 뜻을 가진다


def test_states_jump_never_past_last_card(monkeypatch):
    r = states(monkeypatch, 3, len(CARDS) - 1)
    assert r["decision"] == "next" and r["target"] is None


def test_states_still_like_start_waits(monkeypatch):
    assert states(monkeypatch, 0, 2)["decision"] == "wait"
    assert states(monkeypatch, -1, 2)["decision"] == "wait"


def test_states_similar_step_needs_two_in_a_row(monkeypatch):
    assert states(monkeypatch, 1, 4, similar=True)["decision"] == "wait"
    assert states(monkeypatch, 1, 4, prev_match=4, similar=True)["decision"] == "next"  # prev_match = 끝난 단계 번호(절대)


def test_states_last_card_finishes(monkeypatch):
    assert states(monkeypatch, 1, len(CARDS))["decision"] == "finished"


def test_states_waits_half_the_demo_time(monkeypatch):
    cards = [{"en": "sprinkle", "start": 10, "end": 30}, {"en": "stir", "start": 31, "end": 40}]
    monkeypatch.setattr(coach, "ask_states", lambda c, n, f, r, live=False, action=False: (1, 0, 0.0, {}, coach.view({})))
    assert coach.check(cards, 1, ["f"], 0, False, None, [("a", "u")], -1, False, 4)["decision"] == "wait"  # 20초 단계, 4초째
    assert coach.check(cards, 1, ["f"], 0, False, None, [("a", "u")], -1, False, 11)["decision"] == "next"


def test_states_match_out_of_range_is_ignored(monkeypatch):
    class R:  # 모델이 사진 4장에 9번이라고 답한 경우
        output_text = '{"match": 9, "seen": 2}'
        class usage: input_tokens = 0; output_tokens = 0
    monkeypatch.setattr(coach.pipeline.client.responses, "create", lambda **k: R())
    m, *_ = coach.ask_states(CARDS, 2, ["f"], [("a", "u")] * 4)
    assert m == -1


# 11-03 일반화 개선: 앞서 감(-2) → 다음엔 넓힌다, 막힘 판정, 뒤집기는 동작을 보면 한 번으로
def test_states_further_than_shown_sets_ahead(monkeypatch):
    r = states(monkeypatch, -2, 2)
    assert r["decision"] == "wait" and r["ahead"] is True


def test_stuck_after_twice_the_demo_time():
    cards = [{"en": "fold", "start": 10, "end": 20}]
    assert not coach.stuck(cards, 1, 15) and coach.stuck(cards, 1, 21) and not coach.stuck(cards, 1, None)


def test_lookalike_step_moves_once_when_action_seen(monkeypatch):
    monkeypatch.setattr(coach, "ask_states", lambda c, n, f, r, live=False, action=False: (1, 0, 0.0, {}, {**coach.view({}), "action_seen": action}))
    assert coach.check(CARDS, 2, ["f"] * 4, 0, False, None, [("a", "u")], -1, True)["decision"] == "next"  # 사진 4장: 동작을 봄
    assert coach.check(CARDS, 2, ["f"] * 2, 0, False, None, [("a", "u")], -1, True)["decision"] == "wait"  # 2장뿐: 두 번 확인 규칙
