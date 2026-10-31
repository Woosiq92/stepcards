# 한 언어 더: 번역은 '확인 전'으로 저장되고, 카드 문장이 바뀌면 확인이 풀린다. 숫자 빠짐은 코드가 잡는다
import json
import translate
from test_app import client, make_run, no_network, video  # noqa: F401 (같은 준비를 쓴다)


def fake_ask(answers):
    it = iter(answers)
    return lambda prompt: (next(it), 0.001)


def test_problems_number_and_missing():
    cards = [{"n": 1, "ko": "물 200ml를 부으세요.", "en": "Pour 200 ml of water."}, {"n": 2, "ko": "저으세요.", "en": "Stir."}]
    p = translate.problems(cards, [{"n": 1, "x": "Đổ nước vào."}])
    assert {x["n"]: x["what"] for x in p} == {1: "number", 2: "missing"} and p[0]["detail"] == ["200"]


def test_back_translation_never_sees_source(monkeypatch):
    seen = []
    def ask(prompt):
        seen.append(prompt)
        return ({"name": "Tiếng Việt", "cards": [{"n": 1, "x": "Gấp lên."}]} if len(seen) == 1 else {"cards": [{"n": 1, "ko": "위로 접어.", "en": "Fold up."}]}), 0.001
    monkeypatch.setattr(translate, "_ask", ask)
    out = translate.run([{"n": 1, "ko": "밑단을 위로 접으세요.", "en": "Fold the bottom edge up."}], "Vietnamese")
    assert "밑단" not in seen[1] and "bottom edge" not in seen[1]
    assert out["cards"][0]["xb"] == {"ko": "위로 접어.", "en": "Fold up."} and out["name"] == "Tiếng Việt"


def test_translate_saved_unchecked_then_confirm_then_edit_resets(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(translate, "_ask", fake_ask([{"name": "Tiếng Việt", "cards": [{"n": 1, "x": "Làm số 1."}, {"n": 2, "x": "Làm số 2."}]},
                                                     {"cards": [{"n": 1, "ko": "1번 해.", "en": "Do 1."}, {"n": 2, "ko": "2번 해.", "en": "Do 2."}]}]))
    r = client.post(f"/api/runs/{rid}/translate", json={"lang": "Vietnamese"})
    assert r.status_code == 200 and r.json()["extra"] == {"lang": "Vietnamese", "name": "Tiếng Việt", "ok": False}
    assert r.json()["translate"]["problems"] == []
    cards = r.json()["cards"]
    ok = client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "title": "", "extra": {**r.json()["extra"], "ok": True}}).json()
    assert ok["extra"]["ok"] is True
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "title": ""}).json()["extra"]["ok"] is True  # 편집기 저장(extra 없음)은 그대로
    cards[0]["ko"] = "1번을 천천히 하세요."
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "title": ""}).json()["extra"]["ok"] is False
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "title": "", "extra": None}).json()["extra"] is None


def test_translate_empty_result_is_error(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(translate, "_ask", fake_ask([{"cards": []}]))
    assert client.post(f"/api/runs/{rid}/translate", json={"lang": "中文"}).status_code == 502
    assert "extra" not in json.loads((d / "cards.json").read_text())
