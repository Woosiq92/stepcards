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


def test_hands_visibility_passes_through(monkeypatch):
    # 손·물건이 안 보이면 화면이 카메라 맞추기를 돕는다. 모르면 None(옛 답 형식도 그대로 된다)
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (0, False, 0.0, {}, False))
    assert coach.check(CARDS, 2, ["f"])["hands"] is False
    monkeypatch.setattr(coach, "ask", lambda c, n, f: (0, False, 0.0))
    assert coach.check(CARDS, 2, ["f"])["hands"] is None
