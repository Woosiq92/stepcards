# 저장 공간 관리: 카드 묶음이 계속 쌓여도 볼륨이 차지 않게 단계별로 줄이고, 교사 자료는 따로 백업한다.
# 단계: 만드는 중 → 완성(소리 파일 삭제) → 정리(원본 → 640px 무음 사본, 1초 사진·캐시 삭제) → 보관(카드·그림·글만)
# 설계와 실측 근거: 데이터관리설계.md. 견본(seed)은 이미 작아서 정리·보관·삭제하지 않는다.
import json, os, shutil, subprocess, time, zipfile
from pathlib import Path

COMPACT_DAYS = int(os.environ.get("COMPACT_DAYS", 14))   # 마지막으로 쓴 지 이만큼 지나면 정리
ARCHIVE_DAYS = int(os.environ.get("ARCHIVE_DAYS", 90))   # 이만큼 지나면 보관(영상까지 지움)
RETAIN_DAYS = int(os.environ.get("RETAIN_DAYS", 0))      # 학교가 정하는 삭제 기간(0=끔). 7일 전부터 처음 화면에 알림
CACHE_DAYS = int(os.environ.get("CACHE_DAYS", 30))
TEACHER_QUOTA_MB = int(os.environ.get("TEACHER_QUOTA_MB", 5000))
TEACHER_MAX_SETS = int(os.environ.get("TEACHER_MAX_SETS", 50))
AUDIT_KEEP, BACKUP_KEEP, NOW_KEEP_DAYS = 1000, 7, 7
DAY = 86400


def size(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def progress(d):
    try:
        return json.loads((d / "progress.json").read_text())
    except (OSError, ValueError):
        return {}


def video_of(d):
    v = Path(progress(d).get("video_path") or "")
    return v if v.is_file() else None


def stage(d):
    ev = progress(d).get("events", [])
    if (d / "archived.txt").exists():
        return "archived"
    if (d / "compact.txt").exists():
        return "compact"
    if any(e.get("stage") == "done" for e in ev):
        return "done"
    return "error" if any(e.get("stage") == "error" for e in ev) else "making"


def last_used(d):
    """마지막으로 고치거나 연 때(cards.json 수정·화면에서 연 기록 중 늦은 것)"""
    return max((d / f).stat().st_mtime for f in ("cards.json", "used") if (d / f).exists()) if (d / "cards.json").exists() else 0


def touch_used(d):
    (d / "used").write_text(str(int(time.time())))


def report(d, uploads):
    v = video_of(d)
    own = v and v.resolve().parent == uploads.resolve()
    return {"video": size(v) if v else 0, "frames": size(d / "frames"), "audio": size(d / "audio.wav"),
            "cards": size(d / "cards"), "cache": size(d / "clips") + size(d / "glass"),
            "total": size(d) + (size(v) if own else 0)}


def finalize(d):
    """완성: 받아쓰기가 끝난 소리 파일은 다시 쓰지 않는다"""
    (d / "audio.wav").unlink(missing_ok=True)


def shared(v, runs, me):
    """같은 원본 영상을 다른 카드 묶음도 쓰고 있는지"""
    return any(o != me and o.is_dir() and progress(o).get("video_path") == str(v) for o in runs.iterdir())


def compact(d, runs, uploads):
    """정리: 원본을 640px 무음 사본으로 바꾸고(장면 바꾸기·움직임 카드는 사본으로 계속 된다) 1초 사진·캐시를 지운다"""
    v = video_of(d)
    if stage(d) not in ("done",) or not v:
        return False
    small = d / "video_small.mp4"
    tmp = d / ".video_small.tmp.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(v), "-an", "-vf", "scale='min(640,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)], check=True)
    os.replace(tmp, small)
    p = progress(d)
    p["video_path"] = str(small)
    (d / "progress.json").write_text(json.dumps(p, ensure_ascii=False, indent=1))
    if v.resolve().parent == uploads.resolve() and not shared(v, runs, d):
        v.unlink(missing_ok=True)
    for sub in ("frames", "clips", "glass"):
        shutil.rmtree(d / sub, ignore_errors=True)
    finalize(d)
    (d / "compact.txt").write_text(str(int(time.time())))
    return True


def ensure_frames(d):
    """정리된 카드 묶음에서 장면 고르기를 열면 사본에서 1초 사진을 다시 뽑는다"""
    frames, v = d / "frames", video_of(d)
    if frames.exists() or not v:
        return frames.exists()
    tmp = d / ".frames_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(v), "-vf", "fps=1,scale=-2:360", "-q:v", "6", str(tmp / "f%03d.jpg")], check=True)
    os.replace(tmp, frames)
    return True


def archive(d, runs, uploads):
    """보관: 카드·그림·글만 남기고 영상·사진을 지운다(장면 바꾸기·움직임 카드는 꺼진다)"""
    if stage(d) not in ("done", "compact"):
        return False
    v = video_of(d)
    if v and (v.parent == d or (v.resolve().parent == uploads.resolve() and not shared(v, runs, d))):
        v.unlink(missing_ok=True)
    for sub in ("frames", "clips", "glass", "look"):
        shutil.rmtree(d / sub, ignore_errors=True)
    finalize(d)
    (d / "archived.txt").write_text(str(int(time.time())))
    return True


def delete_on(d):
    """RETAIN_DAYS 가 있으면 지워질 날(초). 없으면 None"""
    return last_used(d) + RETAIN_DAYS * DAY if RETAIN_DAYS and last_used(d) else None


def owned_usage(runs, uploads, owner):
    sets = [d for d in runs.iterdir() if d.is_dir() and (d / "owner.txt").exists() and (d / "owner.txt").read_text().strip() == owner]
    return len(sets), sum(report(d, uploads)["total"] for d in sets)


def trim_audit(d):
    f = d / "audit.jsonl"
    if f.exists():
        lines = f.read_text().splitlines()
        if len(lines) > AUDIT_KEEP:
            f.write_text("\n".join(lines[-AUDIT_KEEP:]) + "\n")


def backup(runs, out_dir, seeds):
    """교사 자료(카드·그림·제목·주인·기록)만 하루 한 번 zip 으로. 영상과 1초 사진은 빼서 작게, 최근 BACKUP_KEEP 개만"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"teacher-{time.strftime('%Y%m%d')}.zip"
    if out.exists():
        return out
    tmp = out.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for d in sorted(runs.iterdir()):
            if not d.is_dir() or d.name in seeds or not (d / "cards.json").exists():
                continue
            for f in ["cards.json", "owner.txt", "audit.jsonl"] + [f"cards/{c.name}" for c in sorted((d / "cards").glob("*"))]:
                if (d / f).exists():
                    z.write(d / f, f"{d.name}/{f}")
    os.replace(tmp, out)
    for old in sorted(out_dir.glob("teacher-*.zip"))[:-BACKUP_KEEP]:
        old.unlink()
    return out


def maintain(runs, uploads, seeds, backups, now_state, running=()):
    """하루 몇 번 도는 정리: 소리 파일·캐시·단계 넘기기·삭제·기록 줄이기·백업. 무엇을 했는지 돌려준다"""
    t, did = time.time(), {"finalized": 0, "compacted": 0, "archived": 0, "deleted": 0, "cache_files": 0}
    for f in list(runs.glob("*/clips/*")) + list(runs.glob("*/glass/*")):
        if t - f.stat().st_mtime > CACHE_DAYS * DAY:
            f.unlink(missing_ok=True)
            did["cache_files"] += 1
    for d in list(runs.iterdir()):
        if not d.is_dir() or d.name in seeds or d.name in running:
            continue
        st, idle = stage(d), t - last_used(d) if last_used(d) else 0
        if st == "done" and (d / "audio.wav").exists():
            finalize(d)
            did["finalized"] += 1
        if RETAIN_DAYS and last_used(d) and idle > RETAIN_DAYS * DAY:
            v = video_of(d)
            shutil.rmtree(d)
            if v and v.resolve().parent == uploads.resolve() and not shared(v, runs, d):
                v.unlink(missing_ok=True)
            did["deleted"] += 1
            continue
        try:
            if st in ("done", "compact") and idle > ARCHIVE_DAYS * DAY:
                did["archived"] += archive(d, runs, uploads)
            elif st == "done" and idle > COMPACT_DAYS * DAY:
                did["compacted"] += compact(d, runs, uploads)
        except (OSError, subprocess.CalledProcessError):
            pass  # 하나가 실패해도 나머지는 계속(다음 차례에 다시)
        trim_audit(d)
    for k in [k for k, v in now_state.items() if t - v.get("t", t) > NOW_KEEP_DAYS * DAY]:
        now_state.pop(k, None)
    backup(runs, backups, seeds)
    return did
