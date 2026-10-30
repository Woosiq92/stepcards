# app.py 버그 재현·회귀 시험. 네트워크(Meta API)를 부르는 경로는 전부 가짜로 바꾼다
import json, os, subprocess, tempfile, threading, uuid
from pathlib import Path

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="stepcards_test_")
import pytest
from fastapi.testclient import TestClient
from PIL import Image
import app as A
import pipeline
REAL_VIDEO_SECONDS = A.video_seconds

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
    monkeypatch.setattr(A, "video_seconds", lambda p: 10)  # 대부분의 시험은 아무 바이트나 '영상'으로 올린다
    monkeypatch.setattr(pipeline, "API_KEY", "test")


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
    monkeypatch.setattr(pipeline, "main", lambda v, **k: calls.append(Path(v)))
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
    assert [p.name for p in (d / "glass").iterdir()] == ["1_02_0_k.jpg"]


# 5. 접속 키에 한글이 와도 500 이 아니라 401
def test_key_non_ascii(monkeypatch):
    monkeypatch.setattr(A, "APP_KEY", "secret")
    assert client.post("/login", data={"k": "한글키"}).status_code == 401
    assert client.post("/login", data={"k": "secret"}).status_code == 200


# 6. 같은 영상을 도는 중에 또 올려도 파이프라인은 하나만
def test_same_video_while_running_starts_once(monkeypatch):
    go, calls = threading.Event(), []
    monkeypatch.setattr(pipeline, "main", lambda v, **k: (calls.append(v), go.wait(5)))
    data = uuid.uuid4().bytes
    ids = {client.post("/api/upload", files={"file": ("x.mp4", data)}).json()["id"] for _ in range(3)}
    go.set()
    assert len(ids) == 1 and len(calls) == 1


def test_done_video_not_rerun(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "main", lambda v, **k: calls.append(v))
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


# 도움 단계는 0~4 로 맞춰 함께 나누고, 안 보내면 0(끔)
def test_now_keeps_help_level():
    rid, d = make_run()
    assert client.post(f"/api/runs/{rid}/now", json={"i": 1, "lv": 3, "by": "coach"}).json()["lv"] == 3
    assert client.post(f"/api/runs/{rid}/now", json={"i": 1, "lv": 9, "by": "glasses"}).json()["lv"] == 4
    assert client.post(f"/api/runs/{rid}/now", json={"i": 0, "by": "glasses"}).json()["lv"] == 0
    assert client.get(f"/api/runs/{rid}/now").json()["lv"] == 0


# 견본 카드 묶음은 빈 저장소에도 들어가 있고, 영상 경로가 새 위치로 맞춰진다
def test_seed_copied():
    d = A.RUNS / "8e1456e529ca"
    assert (d / "cards.json").exists()
    assert json.loads((d / "progress.json").read_text())["video_path"] == str(d / "video.mp4")


# 제목은 저장되고 목록에 나온다. 지우면 폴더도 목록에서도 사라진다
def test_title_and_delete():
    rid, d = make_run()
    cards = json.loads((d / "cards.json").read_text())["cards"]
    assert client.put(f"/api/runs/{rid}/cards", json={"cards": cards, "title": "  라테 만들기 "}).status_code == 200
    assert next(r for r in client.get("/api/runs").json() if r["id"] == rid)["title"] == "라테 만들기"
    assert client.delete(f"/api/runs/{rid}").json()["ok"]
    assert not d.exists() and all(r["id"] != rid for r in client.get("/api/runs").json())
    assert client.delete(f"/api/runs/{rid}").status_code == 404


# 보기(GET)와 지금 카드 맞추기는 키 없이, 돈이 들거나 카드를 바꾸는 요청은 키가 있어야
def test_view_open_actions_need_key(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(A, "APP_KEY", "teach-1")
    c = TestClient(A.app, base_url="https://testserver")
    for u in ("/", f"/glasses?run={rid}", "/api/runs", f"/api/runs/{rid}/cards", f"/api/runs/{rid}/qr.svg?to=glasses"):
        assert c.get(u).status_code == 200, u
    assert c.post(f"/api/runs/{rid}/now", json={"i": 1}).status_code == 200
    for m, u in (("put", f"/api/runs/{rid}/cards"), ("post", f"/api/runs/{rid}/coach"), ("post", f"/api/runs/{rid}/agent"),
                 ("post", "/api/upload"), ("delete", f"/api/runs/{rid}"), ("post", f"/api/runs/{rid}/cards/1/illustrate")):
        assert getattr(c, m)(u).status_code == 401, u
    assert c.post("/login", data={"k": "teach-1"}).status_code == 200 and "sc_key" in c.cookies
    cards = json.loads((d / "cards.json").read_text())["cards"]
    assert c.put(f"/api/runs/{rid}/cards", json={"cards": cards}).status_code == 200


# 멈춘 실행 다시 만들기: 영상이 있으면 한 번만 시작, 없으면 404
def test_retry(monkeypatch):
    rid, d = make_run()
    gate, calls = threading.Event(), []
    monkeypatch.setattr(pipeline, "main", lambda v, **k: (calls.append(v), gate.wait(5)))
    assert client.post(f"/api/runs/{rid}/retry").status_code == 200
    assert client.post(f"/api/runs/{rid}/retry").status_code == 409  # 도는 중
    gate.set()
    p = json.loads((d / "progress.json").read_text()); p["video_path"] = "/nope.mp4"
    (d / "progress.json").write_text(json.dumps(p))
    for _ in range(50):
        if rid not in A.RUNNING: break
        threading.Event().wait(0.05)
    assert client.post(f"/api/runs/{rid}/retry").status_code == 404
    assert len(calls) == 1


# 안경용 그림: 흰 바탕은 검게(렌즈에서 투명), 검은 선은 밝게, 색은 그대로
def test_glass_drawing_dark_background():
    rid, d = make_run()
    im = Image.new("RGB", (100, 60), "white")
    for x in range(30, 70):
        for y in range(20, 40):
            im.putpixel((x, y), (200, 30, 40))
    for x in range(10, 20):
        im.putpixel((x, 50), (0, 0, 0))
    im.save(d / "cards" / "01_ill.jpg")
    data = json.loads((d / "cards.json").read_text())
    data["cards"][0].update(ill="cards/01_ill.jpg", view="ill")
    (d / "cards.json").write_text(json.dumps(data))
    r = client.get(f"/api/runs/{rid}/glass/0.jpg")
    out = Image.open(__import__("io").BytesIO(r.content)).convert("RGB")
    sx = out.width / 100
    assert max(out.getpixel((2, 2))) < 30                                   # 바탕 → 검정
    assert out.getpixel((int(50 * sx), int(30 * sx)))[0] > 150              # 빨강 그대로
    assert min(out.getpixel((int(15 * sx), int(50 * sx)))) > 120             # 검은 선 → 밝게


# 이 맥에서 만들기: Glimmer 가 꺼져 있으면 409, 켜져 있으면 local 로 넘기고, 다시 만들기도 같은 곳으로
def test_upload_local(monkeypatch):
    import coach
    calls, gate = [], threading.Event()
    monkeypatch.setattr(pipeline, "main", lambda v, **k: (calls.append(k), gate.wait(5)))
    monkeypatch.setattr(coach, "local_ready", lambda: False)
    assert client.post("/api/upload", files={"file": ("a.mp4", uuid.uuid4().bytes)}, data={"local": "true"}).status_code == 409
    monkeypatch.setattr(coach, "local_ready", lambda: True)
    assert client.post("/api/upload", files={"file": ("a.mp4", uuid.uuid4().bytes)}, data={"local": "true"}).status_code == 200
    gate.set()
    assert calls == [{"local": True}]


# 심사위원 키: 다 해 볼 수 있지만 크레딧이 드는 요청은 하루 한도까지
def test_judge_key_daily_limit(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(A, "APP_KEY", "teach-1"); monkeypatch.setattr(A, "JUDGE_KEY", "judge-9")
    monkeypatch.setitem(A.JUDGE_LIMITS, "agent", 2); A.JUDGE_USE.update(day="", n={})
    import agent
    monkeypatch.setattr(agent, "run", lambda *a: {"changes": [], "note": "", "problems": [], "checks": 0, "cost": 0})
    c = TestClient(A.app, base_url="https://testserver")
    assert c.post("/login", data={"k": "judge-9"}).status_code == 200 and "sc_judge" in c.cookies
    cards = json.loads((d / "cards.json").read_text())["cards"]
    assert c.put(f"/api/runs/{rid}/cards", json={"cards": cards}).status_code == 200   # 저장은 세지 않음
    codes = [c.post(f"/api/runs/{rid}/agent", json={"instruction": "x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# 키가 없으면 목록에는 견본만, 올린 카드 묶음은 주소로는 열림
def test_unlisted_without_key(monkeypatch):
    rid, d = make_run()
    monkeypatch.setattr(A, "APP_KEY", "teach-1")
    c = TestClient(A.app, base_url="https://testserver")
    ids = [r["id"] for r in c.get("/api/runs").json()]
    assert rid not in ids and all(i in A.SEED_INDEX for i in ids)
    assert c.get(f"/api/runs/{rid}/cards").status_code == 200
    c.cookies.set("sc_key", "teach-1")
    assert rid in [r["id"] for r in c.get("/api/runs").json()]


# 서버가 다시 켜지면 끝나지 않은 만들기는 '멈춤'으로 표시
def test_mark_interrupted():
    rid, d = make_run()
    (d / "progress.json").write_text(json.dumps({"video": "v.mp4", "video_path": "", "events": [{"stage": "start"}, {"stage": "extract"}]}))
    A.mark_interrupted()
    assert json.loads((d / "progress.json").read_text())["events"][-1]["stage"] == "error"


# 길이가 0(영상 아님)이면 거절, 키가 없으면 API 로 만들기는 503
def test_upload_checks(monkeypatch):
    monkeypatch.setattr(A, "video_seconds", REAL_VIDEO_SECONDS)
    assert client.post("/api/upload", files={"file": ("x.mp4", b"not a video")}).status_code == 400
    monkeypatch.setattr(pipeline, "API_KEY", "")
    assert client.post("/api/upload", files={"file": ("v.mp4", VIDEO.read_bytes())}).status_code == 503


# 교사 키: 자기가 올린 것만 고치고 지운다(따라 하기는 누구 것이든), 목록에는 견본+자기 것, 바꾼 것은 기록
def test_teacher_keys(monkeypatch):
    mine, dm = make_run(); other, do = make_run()
    (dm / "owner.txt").write_text("teacher:kim"); (do / "owner.txt").write_text("teacher:lee")
    monkeypatch.setattr(A, "APP_KEY", "admin-1"); monkeypatch.setattr(A, "TEACHERS", {"kim": "kk-1", "lee": "ll-2"})
    c = TestClient(A.app, base_url="https://testserver")
    assert c.post("/login", data={"k": "kk-1"}).status_code == 200 and "sc_teacher" in c.cookies
    ids = [r["id"] for r in c.get("/api/runs").json()]
    assert mine in ids and other not in ids
    cards = json.loads((dm / "cards.json").read_text())["cards"]
    assert c.put(f"/api/runs/{mine}/cards", json={"cards": cards}).status_code == 200
    assert c.put(f"/api/runs/{other}/cards", json={"cards": cards}).status_code == 403
    assert c.delete(f"/api/runs/{other}").status_code == 403
    assert "teacher:kim" in (dm / "audit.jsonl").read_text()


# 같은 카드 묶음도 짝 코드가 다르면 따로 넘어간다, 상태는 파일에 남는다
def test_now_sessions():
    rid, d = make_run()
    client.post(f"/api/runs/{rid}/now", json={"i": 1, "s": "ab12"})
    assert client.get(f"/api/runs/{rid}/now", params={"s": "ab12"}).json()["i"] == 1
    assert client.get(f"/api/runs/{rid}/now", params={"s": "zz99"}).json()["i"] == 0
    assert f"{rid}|ab12" in json.loads(A.STATE.read_text())["now"]


def test_health_and_export():
    rid, d = make_run()
    h = client.get("/api/health").json()
    assert h["ok"] in (True, False) and "free_gb" in h
    r = client.get(f"/api/runs/{rid}/export.zip")
    import zipfile, io as _io
    names = zipfile.ZipFile(_io.BytesIO(r.content)).namelist()
    assert "cards.json" in names and "cards/01.jpg" in names
