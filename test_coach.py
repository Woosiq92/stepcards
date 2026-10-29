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
