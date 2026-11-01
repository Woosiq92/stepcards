# 3D 접기 서버 경로: 프로그램 받기·비교는 저장하지 않고, 저장은 형식이 맞을 때만. 모델 호출은 가짜로
import json
from PIL import Image
import fold_gen
from test_app import client, make_run, no_network, video  # noqa: F401


def frames(d, n=4):
    (d / "frames").mkdir(exist_ok=True)
    for i in range(1, n + 1):
        Image.new("RGB", (32, 32), "red").save(d / "frames" / f"f{i:03d}.jpg")


def test_step_writes_one_card_with_shape_on_first(monkeypatch):
    rid, d = make_run(); frames(d)
    seen = []
    monkeypatch.setattr(fold_gen, "_ask", lambda content, effort=None: (seen.append(content), ({"shape": {"w": 1, "h": 1, "color": "red"}, "ops": [{"op": "flip"}]}, 0.01))[1])
    r = client.post(f"/api/runs/{rid}/fold/step", json={"n": 1, "prefix": {"steps": []}})
    assert r.status_code == 200 and r.json()["ops"] == [{"op": "flip"}] and r.json()["shape"]["color"] == "#c0392b"  # 색은 #rrggbb 만
    assert sum(1 for x in seen[0] if x["type"] == "input_image") == 2  # 앞 단계 끝 + 이번 단계 끝
    assert "fold" not in json.loads((d / "cards.json").read_text())  # 저장하지 않는다


def test_step_sends_current_shape_and_problems(monkeypatch):
    rid, d = make_run(); frames(d)
    seen = []
    monkeypatch.setattr(fold_gen, "_ask", lambda content, effort=None: (seen.append(content), ({"ops": []}, 0))[1])
    r = client.post(f"/api/runs/{rid}/fold/step", json={"n": 2, "prefix": {"steps": [{"n": 1, "ops": []}]}, "current": "data:image/jpeg;base64,AAAA",
                                                        "problems": ["card n=2: nothing moves"], "notes": ["fold the other corner"]})
    assert r.json() == {"ops": [], "cost": 0}  # 둘째 카드부터는 shape 없음
    assert sum(1 for x in seen[0] if x["type"] == "input_image") == 3  # 지금 3D 모양 그림까지
    assert "nothing moves" in seen[0][-1]["text"] and "other corner" in seen[0][-1]["text"]
    assert client.post(f"/api/runs/{rid}/fold/step", json={"n": 99, "prefix": {}}).status_code == 502


def test_compare_only_takes_jpeg_stills(monkeypatch):
    rid, d = make_run(); frames(d)
    seen = []
    monkeypatch.setattr(fold_gen, "_ask", lambda content, effort=None: (seen.append(content), ({"cards": [{"n": 1, "match": "maybe"}]}, 0))[1])
    r = client.post(f"/api/runs/{rid}/fold/compare", json={"stills": {"1": "data:image/jpeg;base64,AAAA", "2": "http://x/y.jpg"}})
    assert r.json()["cards"] == [{"n": 1, "match": "unclear", "fix": ""}]
    assert sum(1 for x in seen[0] if x["type"] == "input_image") == 2  # 카드 1만(시범 + 3D)


def test_save_fold_validated_and_removable():
    rid, d = make_run()
    cards = json.loads((d / "cards.json").read_text())["cards"]
    prog = {"shape": {"w": 1, "h": 1}, "steps": [{"n": 1, "ops": [{"op": "fold", "from": "bottom", "to": "top"}]}]}
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "fold": prog}).json()["fold"] == prog
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards}).json()["fold"] == prog  # 편집기 저장은 그대로
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "fold": "bad"}).json()["fold"] is None
