# 저장 공간 관리: 단계별로 줄이기·보관·백업·한도·관리자 화면(유료 호출 없음, 작은 시험 영상 사용)
import json, os, time, zipfile
import test_app as T  # 같은 임시 저장소·시험 영상·make_run 을 쓴다
from test_app import A, client, make_run, VIDEO, video, no_network  # 시험 영상 만들기·유료 호출 막기 고정 장치도 같이
import storage


def done_run(video=VIDEO):
    rid, d = make_run()
    p = json.loads((d / "progress.json").read_text()); p["video_path"] = str(video); p["events"] = [{"stage": "start"}, {"stage": "done"}]
    (d / "progress.json").write_text(json.dumps(p))
    (d / "frames").mkdir(); (d / "frames" / "f001.jpg").write_bytes(b"x")
    (d / "audio.wav").write_bytes(b"0" * 1000)
    return rid, d


def test_compact_then_frames_then_archive(video):
    rid, d = done_run()
    assert storage.compact(d, A.RUNS, A.UPLOADS)
    assert storage.stage(d) == "compact" and not (d / "frames").exists() and not (d / "audio.wav").exists()
    assert storage.video_of(d).name == "video_small.mp4" and VIDEO.exists()  # 업로드 폴더 밖 영상은 지우지 않는다
    assert client.post(f"/api/runs/{rid}/frames").json()["ok"] and len(list((d / "frames").glob("*.jpg"))) >= 2
    assert client.get(f"/api/runs/{rid}/clip/1.mp4").status_code == 200   # 사본으로 움직임 카드
    assert storage.archive(d, A.RUNS, A.UPLOADS) and storage.stage(d) == "archived"
    assert not (d / "video_small.mp4").exists() and client.get(f"/api/runs/{rid}/clip/2.mp4").status_code == 409
    assert client.get(f"/api/runs/{rid}/cards").json()["stage"] == "archived"


def test_maintain_by_age(monkeypatch, video):
    rid, d = done_run()
    old = time.time() - 20 * 86400
    os.utime(d / "cards.json", (old, old))
    did = storage.maintain(A.RUNS, A.UPLOADS, set(A.SEED_INDEX), A.DATA / "backups", {})
    assert storage.stage(d) == "compact" and did["compacted"] >= 1
    assert list((A.DATA / "backups").glob("teacher-*.zip"))
    names = zipfile.ZipFile(sorted((A.DATA / "backups").glob("teacher-*.zip"))[-1]).namelist()
    assert f"{rid}/cards.json" in names and not any(n.endswith(".mp4") for n in names)
    monkeypatch.setattr(storage, "RETAIN_DAYS", 10)
    storage.maintain(A.RUNS, A.UPLOADS, set(A.SEED_INDEX), A.DATA / "backups", {})
    assert not d.exists()


def test_quota_and_admin(monkeypatch):
    monkeypatch.setattr(A, "APP_KEY", "admin-1"); monkeypatch.setattr(A, "TEACHERS", {"kim": "kk-1"})
    monkeypatch.setattr(storage, "TEACHER_MAX_SETS", 1)
    rid, d = make_run(); (d / "owner.txt").write_text("teacher:kim")
    c = T.TestClient(A.app, base_url="https://testserver")
    c.post("/login", data={"k": "kk-1"})
    assert c.post("/api/upload", files={"file": ("q.mp4", os.urandom(64))}).status_code == 403   # 한도(1묶음) 넘음
    assert c.get("/api/admin/storage").status_code == 403
    a = T.TestClient(A.app, base_url="https://testserver"); a.post("/login", data={"k": "admin-1"})
    rep = a.get("/api/admin/storage").json()
    assert any(r["id"] == rid and r["owner"] == "teacher:kim" for r in rep["runs"]) and "teacher:kim" in rep["owners"]
