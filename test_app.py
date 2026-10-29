# app.py 버그 재현·회귀 시험. 네트워크(Meta API)를 부르는 경로는 전부 가짜로 바꾼다
import json, os, subprocess, tempfile, threading, uuid
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="stepcards_test_")
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import app as A
import pipeline

client = TestClient(A.app, raise_server_exceptions=False)
VIDEO = Path(os.environ["DATA_DIR"]) / "test.mp4"


@pytest.fixture(scope="module", autouse=True)
def video():
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x180:rate=10",
                    "-pix_fmt", "yuv420p", str(VIDEO)], check=True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("네트워크 경로 호출")
    for f in ("main", "find_box", "illustrate"):
        monkeypatch.setattr(pipeline, f, boom)


def make_run(cards=None):
    rid = uuid.uuid4().hex[:12]
    d = A.RUNS / rid
    (d / "cards").mkdir(parents=True)
    for i in (1, 2):
        Image.new("RGB", (64, 64), "red").save(d / "cards" / f"0{i}.jpg")
    cards = cards or [{"n": i, "start": 0, "end": 3, "rep": 1, "ko": f"{i}번을 하세요.", "en": "Do.", "object": "cup",
                       "image": f"cards/0{i}.jpg"} for i in (1, 2)]
    (d / "cards.json").write_text(json.dumps({"duration": 3, "problems": [], "warnings": [], "cards": cards}))
    (d / "progress.json").write_text(json.dumps({"video": VIDEO.name, "video_path": str(VIDEO), "events": []}))
    return rid, d


# 1. 이름이 같은 다른 영상이 옛 업로드를 덮지 않는다
def test_upload_same_name_does_not_overwrite(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "main", lambda v: calls.append(Path(v)))
    a = client.post("/api/upload", files={"file": ("same.mp4", b"AAAA")}).json()["id"]
    b = client.post("/api/upload", files={"file": ("same.mp4", b"BBBB")}).json()["id"]
    assert a != b
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(2)
    assert [p.read_bytes() for p in calls] == [b"AAAA", b"BBBB"]


# 2. reframe 가 느린 일을 하는 사이 저장된 다른 카드 편집을 잃지 않는다
def test_reframe_keeps_concurrent_edit(monkeypatch):
    rid, d = make_run()

    def find_box(img, card):  # SAM 대신: 도는 사이 자동 저장이 2번 카드를 고친다
        body = read_cards(d)
        body["cards"][1]["ko"] = "고친 문장이에요."
        A.save(rid, body)
        return None, "cup", False
    monkeypatch.setattr(pipeline, "find_box", find_box)
    r = client.post(f"/api/runs/{rid}/cards/1/frame", params={"t": 1})
    assert r.status_code == 200, r.text
    cs = read_cards(d)["cards"]
    assert cs[1]["ko"] == "고친 문장이에요." and cs[0]["frame_t"] == 1


def read_cards(d):
    return json.loads((d / "cards.json").read_text())


# 3. 카드의 image/ill 경로로 실행 폴더 밖을 건드리지 못한다
def test_save_rejects_path_traversal():
    rid, d = make_run()
    body = read_cards(d)
    for bad in ("../../x.jpg", "/etc/passwd", "cards/../../progress.json", "cards/a/../../x.jpg"):
        body["cards"][0]["image"] = bad
        assert client.put(f"/api/runs/{rid}/cards", json=body).status_code == 400, bad
    body["cards"][0]["image"] = "cards/01.jpg"
    body["cards"][0]["ill"] = "../evil.jpg"
    assert client.put(f"/api/runs/{rid}/cards", json=body).status_code == 400
    body["cards"][0]["ill"] = "cards/01_ill.jpg"
    assert client.put(f"/api/runs/{rid}/cards", json=body).status_code == 200


def test_use_sites_guard_stored_bad_path():
    outside = A.RUNS / "outside.jpg"
    Image.new("RGB", (8, 8)).save(outside)
    rid, d = make_run()
    data = read_cards(d)
    data["cards"][0]["image"] = "../outside.jpg"  # 검사 전에 저장된 옛 파일이라고 치자
    (d / "cards.json").write_text(json.dumps(data))
    assert client.get(f"/api/runs/{rid}/glass/0.jpg").status_code == 400
    assert client.post(f"/api/runs/{rid}/cards/1/frame", params={"t": 1}).status_code == 400
    assert outside.exists()


# 4. 캐시 파일: 실패한 ffmpeg 가 반쪽 파일을 남기지 않고, 성공하면 제자리에 놓인다
def test_clip_failure_leaves_no_cache(monkeypatch):
    rid, d = make_run()

    def bad_clip(video, t0, dur, out, width):
        Path(out).write_bytes(b"partial")
        raise subprocess.CalledProcessError(1, "ffmpeg")
    monkeypatch.setattr(pipeline, "clip", bad_clip)
    assert client.get(f"/api/runs/{rid}/clip/1.mp4").status_code == 500
    assert list((d / "clips").glob("*")) == []


def test_clip_and_glass_cache_ok():
    rid, d = make_run()
    r = client.get(f"/api/runs/{rid}/clip/1.mp4", params={"g": 1})
    assert r.status_code == 200 and r.content[4:8] == b"ftyp"
    assert [p.name for p in (d / "clips").iterdir()] == ["1_0_3_1.mp4"]
    r = client.get(f"/api/runs/{rid}/glass/1.jpg")
    assert r.status_code == 200 and r.content[:2] == b"\xff\xd8"
    assert [p.name for p in (d / "glass").iterdir()] == ["1_02_0.jpg"]


# 5. 접속 키에 한글이 와도 500 이 아니라 401
def test_key_non_ascii(monkeypatch):
    monkeypatch.setattr(A, "APP_KEY", "secret")
    assert client.get("/", params={"k": "한글키"}).status_code == 401
    assert client.post("/login", data={"k": "한글키"}).status_code == 401
    assert client.get("/", params={"k": "secret"}, follow_redirects=False).status_code == 303


# 6. 같은 영상을 도는 중에 또 올려도 파이프라인은 하나만
def test_same_video_while_running_starts_once(monkeypatch):
    go, calls = threading.Event(), []
    monkeypatch.setattr(pipeline, "main", lambda v: (calls.append(v), go.wait(5)))
    data = uuid.uuid4().bytes
    ids = {client.post("/api/upload", files={"file": ("x.mp4", data)}).json()["id"] for _ in range(3)}
    go.set()
    assert len(ids) == 1 and len(calls) == 1


def test_done_video_not_rerun(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "main", lambda v: calls.append(v))
    data = uuid.uuid4().bytes
    rid = client.post("/api/upload", files={"file": ("y.mp4", data)}).json()["id"]
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(2)
    (A.RUNS / rid / "progress.json").write_text(json.dumps({"video": "y.mp4", "video_path": "", "events": [{"stage": "done", "msg": ""}]}))
    assert client.post("/api/upload", files={"file": ("y.mp4", data)}).json()["id"] == rid
    assert len(calls) == 1


# 7. 없는 카드 번호는 404
def test_glass_and_clip_unknown_card_404():
    rid, d = make_run()
    assert client.get(f"/api/runs/{rid}/glass/5.jpg").status_code == 404
    assert client.get(f"/api/runs/{rid}/glass/-1.jpg").status_code == 404
    assert client.get(f"/api/runs/{rid}/clip/9.mp4").status_code == 404
    (d / "cards.json").unlink()
    assert client.get(f"/api/runs/{rid}/glass/0.jpg").status_code == 404
