# 교사 지시 에이전트: 모델 대신 가짜 답으로, 검사기 도구가 불리고 최종 판정이 코드로 나오는지 본다(유료 호출 없음)
import json
from types import SimpleNamespace as NS
import agent

CARDS = [{"n": i, "start": i * 10, "end": i * 10 + 8, "rep": i * 10 + 4, "ko": f"컵을 {i}번 놓으세요.", "en": f"Place cup {i}.",
          "object": "cup", "look": "white cup"} for i in (1, 2, 3)]


def fake(replies):
    calls = []

    class Item(NS):
        def model_dump(self, **k):
            return {"type": self.type, "call_id": self.call_id, "name": "check_cards", "arguments": self.arguments}

    def create(**kw):
        calls.append({**kw, "input": list(kw["input"])})  # 같은 목록이 계속 늘어나므로 그때 모습을 복사
        kind, payload = replies.pop(0)
        usage = NS(input_tokens=1000, output_tokens=100)
        if kind == "tool":
            return NS(output=[Item(type="function_call", call_id=f"c{len(calls)}", arguments=json.dumps({"changes": payload}))], usage=usage, output_text="")
        return NS(output=[NS(type="message")], usage=usage, output_text=json.dumps(payload, ensure_ascii=False))
    return create, calls


def test_agent_checks_then_answers(monkeypatch):
    bad = [{"n": 2, "ko": "컵을 들고 천천히 놓으세요.", "en": "Pick up and place."}]
    good = [{"n": 2, "ko": "컵을 놓으세요.", "en": "Place the cup."}]
    create, calls = fake([("tool", bad), ("tool", good), ("final", {"changes": good + [{"n": 9, "ko": "x", "en": "y"}], "note": "더 쉽게 바꿨어요."})])
    monkeypatch.setattr(agent.client.responses, "create", create)
    r = agent.run(CARDS, 40, "더 쉽게")
    first = json.loads(calls[1]["input"][-1]["output"])
    assert first["ok"] is False and first["problems"]          # 동작 둘 → 검사기가 알려 줌
    assert json.loads(calls[2]["input"][-1]["output"])["ok"]   # 고친 안은 통과
    assert [c["n"] for c in r["changes"]] == [2]                # 없는 카드(9)는 버림
    assert r["changes"][0]["ko_before"] == "컵을 2번 놓으세요." and r["problems"] == [] and r["checks"] == 2


def test_agent_unchanged_or_garbage(monkeypatch):
    create, _ = fake([("final", {"changes": [{"n": 1, "ko": "컵을 1번 놓으세요.", "en": "Place cup 1."}]})])
    monkeypatch.setattr(agent.client.responses, "create", create)
    assert agent.run(CARDS, 40, "그대로")["changes"] == []
    create, _ = fake([("final", "not json")])
    monkeypatch.setattr(agent.client.responses, "create", create)
    assert agent.run(CARDS, 40, "?")["changes"] == []
