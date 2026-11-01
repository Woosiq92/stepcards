# 확인하기: 코드 정리 규칙, API(모델은 가짜), 기록은 켰을 때만·키 있는 사람만, 안경 중계 필드
import base64, io, json
from PIL import Image
import test_app as T
from test_app import A, client, make_run, VIDEO, video, no_network
import verify

CARD = {"n": 1, "ko": "밑단을 위로 접으세요.", "en": "Fold the bottom edge up."}


def photo():
    b = io.BytesIO(); Image.new("RGB", (64, 48), "white").save(b, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def test_tidy_rules():
    assert verify.tidy({"result": "done", "confidence": 0.9, "hint_ko": "x"}, CARD) == {"result": "done", "hint_ko": "", "hint_en": "", "confidence": 0.9}
    assert verify.tidy({"result": "different", "confidence": 0.3}, CARD)["result"] == "unclear"        # 확신 낮음
    assert verify.tidy({"result": "weird", "confidence": 1}, CARD)["result"] == "unclear"              # 모르는 결과
    r = verify.tidy({"result": "different", "confidence": 0.8, "hint_ko": "아" * 40, "hint_en": "x"}, CARD)
    assert r["hint_ko"] == CARD["ko"] and r["hint_en"] == CARD["en"]                                   # 너무 긴 안내 → 카드 문장
    r = verify.tidy({"result": "not_yet", "confidence": 0.8, "hint_ko": "끝까지 접으세요.", "hint_en": "Fold all the way."}, CARD)
    assert r["hint_ko"] == "끝까지 접으세요." and r["result"] == "not_yet"


def test_verify_api_and_records(monkeypatch, video):
    rid, d = make_run()
    p = json.loads((d / "progress.json").read_text()); p["video_path"] = str(VIDEO); (d / "progress.json").write_text(json.dumps(p))
    seen = {}
    def fake(card, before, after, ph, local=False):
        seen.update(card=card["n"], imgs=[before[:22], after[:22], ph[:22]], local=local)
        return {"result": "different", "confidence": 0.9, "hint_ko": "끝까지 접으세요.", "hint_en": "Fold all the way."}, 0.004
    monkeypatch.setattr(verify, "ask", fake)
    r = client.post(f"/api/runs/{rid}/cards/1/verify", json={"photo": photo(), "record": True, "lv": 2, "s": "ab12"}).json()
    assert r["result"] == "different" and r["hint_ko"] == "끝까지 접으세요." and seen["imgs"] == ["data:image/jpeg;base64"] * 3
    assert list((d / "cards").glob("01_after_*.jpg")) and list((d / "cards").glob("01_before_*.jpg"))   # 기준 사진은 영상에서
    assert client.get(f"/api/runs/{rid}/cards/1/after.jpg").status_code == 200
    assert client.post(f"/api/runs/{rid}/cards/1/verify", json={"photo": "nope"}).status_code == 400
    rows = client.get(f"/api/runs/{rid}/records").json()
    assert rows[-1]["kind"] == "verify" and rows[-1]["result"] == "different" and rows[-1]["lv"] == 2
    client.post(f"/api/runs/{rid}/cards/1/verify", json={"photo": photo()})                           # 기록 끔
    assert len(client.get(f"/api/runs/{rid}/records").json()) == len(rows)


def test_records_need_key(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(A, "APP_KEY", "admin-1")
    c = T.TestClient(A.app, base_url="https://testserver")
    assert c.get(f"/api/runs/{rid}/records").status_code == 401
    monkeypatch.setitem(A.PUBLIC_LIMITS, "verify", 0)  # 확인은 크레딧이 든다: 키 없는 학습자 기기는 카드 묶음별 하루 한도 안에서만(11-01 A안)
    assert c.post(f"/api/runs/{rid}/cards/1/verify", json={"photo": photo()}).status_code == 429


def test_glasses_relay():
    rid, d = make_run()
    client.post(f"/api/runs/{rid}/now", json={"i": 0, "by": "glasses", "vreq": 3, "s": "x1"})
    assert client.get(f"/api/runs/{rid}/now", params={"s": "x1"}).json()["vreq"] == 3
    client.post(f"/api/runs/{rid}/now", json={"i": 0, "by": "coach", "s": "x1", "vres": {"result": "done", "id": 3}})
    assert client.get(f"/api/runs/{rid}/now", params={"s": "x1"}).json()["vres"]["result"] == "done"


def test_facing_reference_is_mid_step(tmp_path):
    # 수어·춤처럼 마주 보고 찍은 시범: 끝 뒤 2초는 손을 내린 쉬는 자세라 기준이 동작 한가운데여야 한다(11-01 진단)
    import json, verify
    cards = [{"n": 1, "start": 10, "end": 20}, {"n": 2, "start": 30, "end": 40}]
    (tmp_path / "cards.json").write_text(json.dumps({"cards": cards, "duration": 50}))
    assert verify.after_t(tmp_path, cards[0]) == 22  # 1인칭: 끝 + 2초
    (tmp_path / "cards.json").write_text(json.dumps({"cards": cards, "duration": 50, "pov": "facing"}))
    assert verify.after_t(tmp_path, cards[0]) == 15


def test_now_merge_keeps_glasses_changes():
    # 11-01 검수: 휴대폰의 평소 동기화가 안경의 확인 요청을 지우거나, 안경이 넘긴 카드를 되돌리지 않는다
    rid, d = make_run()
    c = lambda body: client.post(f"/api/runs/{rid}/now", json={**body, "s": "mg1"}).json()
    v0 = c({"i": 0, "by": "coach", "base": 0})["v"]
    g = c({"i": 1, "by": "glasses", "vreq": 77})             # 안경: 다음 카드 + 확인 요청
    held = c({"i": 0, "by": "coach", "base": v0})            # 휴대폰이 안경 변경을 못 본 채 옛 카드 번호
    assert held["held"] and held["i"] == 1 and held["vreq"] == 77
    ok = c({"i": 1, "by": "coach", "base": g["v"]})          # 다음 폴링에서 받아 적용한 뒤
    assert not ok.get("held") and ok["i"] == 1 and ok["vreq"] == 77   # 확인 요청은 그대로(휴대폰이 처리할 때까지)
    r = c({"i": 1, "by": "coach", "base": ok["v"], "vres": {"result": "done", "id": "77"}})
    assert r["vres"]["result"] == "done"
    assert c({"i": 1, "by": "coach", "base": r["v"]})["vres"]["result"] == "done"  # 다음 동기화가 결과를 지우지 않는다
