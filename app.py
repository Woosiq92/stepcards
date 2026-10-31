# 로컬 서버: 영상 올리기 → 파이프라인 → 진행판·편집·인쇄·태블릿 보기
# 사용: .venv/bin/python app.py  → http://127.0.0.1:8790
import hashlib, hmac, io, json, os, re, shutil, threading, time, uuid
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
import coach
import pipeline
import storage
import verify
import voice
from check import check

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("DATA_DIR") or ROOT)  # 배포 때는 영구 저장소(예: Railway 볼륨 /data)
RUNS = DATA / "runs"
UPLOADS = DATA / "samples" / "uploads"
RUNS.mkdir(parents=True, exist_ok=True)
SEED = ROOT / "seed"  # 새로 배포해도 바로 볼 수 있는 견본 카드 묶음(CC BY 영상). 지워도 서버를 다시 켜면 돌아온다
SEED_INDEX = json.loads((SEED / "index.json").read_text()) if (SEED / "index.json").exists() else {}  # 견본마다 제목과 쓰임새(처음 화면 '이런 곳에 써요' 예시)
for s in sorted(SEED.iterdir()) if SEED.is_dir() else []:
    if not s.is_dir():
        continue
    new = not (RUNS / s.name).exists()
    for f in s.rglob("*"):  # 빠진 파일만 채운다(교사가 고친 cards.json 은 그대로)
        dst = RUNS / s.name / f.relative_to(s)
        if f.is_file() and (not dst.exists() or (f.name == "video.mp4" and dst.stat().st_size != f.stat().st_size)):
            (RUNS / s.name / f.relative_to(s)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, RUNS / s.name / f.relative_to(s))
    if new:
        p = json.loads((RUNS / s.name / "progress.json").read_text())
        p["video_path"] = str(RUNS / s.name / "video.mp4")
        (RUNS / s.name / "progress.json").write_text(json.dumps(p, ensure_ascii=False))


def mark_interrupted():
    """서버가 다시 켜지면 그 전에 돌던 만들기는 사라진다 → '멈춤'으로 적어 '다시 만들기'가 나오게"""
    for p in RUNS.glob("*/progress.json"):
        try:
            prog = json.loads(p.read_text())
        except (OSError, ValueError):
            continue
        ev = prog.get("events", [])
        if ev and not any(e.get("stage") in ("done", "error") for e in ev):
            ev.append({"t": round(time.time(), 1), "stage": "error", "msg": "멈췄어요: 서버가 다시 시작돼서 만들던 작업이 끊겼어요"})
            p.write_text(json.dumps(prog, ensure_ascii=False, indent=1))


mark_interrupted()


APP_KEY = os.environ.get("APP_KEY", "")  # 공개 주소에 올릴 때만 설정: 키를 아는 사람만 크레딧을 쓰고 카드를 바꾸게
JUDGE_KEY = os.environ.get("JUDGE_KEY", "")  # 심사위원용 키: 다 해 볼 수 있지만 하루 한도가 있다(제출 설명에 적는 키)
JUDGE_LIMITS = {"upload": 6, "illustrate": 60, "agent": 20, "coach": 900, "frame": 60, "retry": 6, "verify": 300}  # 하루 횟수. 따라 하기 900번 ≈ 30분
JUDGE_USE = {"day": "", "n": {}}
TEACHERS = dict(x.strip().split(":", 1) for x in os.environ.get("TEACHER_KEYS", "").split(",") if ":" in x)  # 교사별 키 "이름:키,이름:키"
NOW_PATH = re.compile(r"/api/runs/\w+/now$")
RUN_PATH = re.compile(r"/api/runs/(\w+)(?=/|$)")
STATE = DATA / "state.json"  # 안경·따라 하기 맞추기 상태와 심사용 키 사용량: 서버를 다시 켜도 이어지게


def load_state():
    try:
        st = json.loads(STATE.read_text())
        NOW.update(st.get("now", {})); JUDGE_USE.update(st.get("judge", {}))
    except (OSError, ValueError):
        pass


def save_state():
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"now": NOW, "judge": JUDGE_USE}, ensure_ascii=False))
    os.replace(tmp, STATE)
NOW = {}
load_state()
app = FastAPI()


def eq(a, b):
    return bool(b) and hmac.compare_digest(a.encode(), b.encode())


def who(request):
    """요청한 사람: admin(APP_KEY) / teacher:이름(TEACHER_KEYS) / judge / ''(키 없음). 키를 설정하지 않은 로컬은 admin"""
    if not APP_KEY:
        return "admin"
    c = request.cookies
    if eq(c.get("sc_key", ""), APP_KEY):
        return "admin"
    name = next((n for n, k in TEACHERS.items() if eq(c.get("sc_teacher", ""), k)), None)
    if name:
        return "teacher:" + name
    return "judge" if eq(c.get("sc_judge", ""), JUDGE_KEY) else ""


def has_key(request):
    return bool(who(request))


def owner_of(run_id):
    f = RUNS / run_id / "owner.txt"
    return f.read_text().strip() if f.exists() else ""


@app.middleware("http")
async def need_key(request: Request, call_next):
    """보기(GET)는 누구나. 돈이 들거나 데이터를 바꾸는 요청만 키(쿠키)가 있어야 한다.
    교사 키는 자기가 올린 카드 묶음만 고치고 지울 수 있다(따라 하기는 누구 것이든). 바꾸는 요청은 카드 묶음마다 기록을 남긴다.
    키는 화면 안 입력 칸에서 POST /login 으로 받는다. 안경·따라 하기의 지금 카드 맞추기(/now)는 키 없이"""
    path = request.url.path
    if not APP_KEY or request.method in ("GET", "HEAD") or NOW_PATH.match(path):
        return await call_next(request)
    if path == "/login" and request.method == "POST":
        k = str((await request.form()).get("k", ""))
        for name, key in [("sc_key", APP_KEY), ("sc_judge", JUDGE_KEY)] + [("sc_teacher", tk) for tk in TEACHERS.values()]:
            if eq(k, key):
                r = JSONResponse({"ok": True})
                r.set_cookie(name, key, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax")
                return r
        return JSONResponse({"error": "wrong key"}, 401)
    role = who(request)
    if not role:
        return JSONResponse({"error": "key required"}, 401)
    m = RUN_PATH.match(path)
    use_only = path.endswith(("/coach", "/verify", "/records"))  # 따라 하기·확인하기·기록은 누구 카드 묶음이든(고치기가 아님)
    if m and role.startswith("teacher:") and not use_only and owner_of(m.group(1)) != role:
        return JSONResponse({"error": "another teacher's card set"}, 403)
    if role == "judge":
        kind = next((k for k in JUDGE_LIMITS if path.rstrip("/").endswith(k)), None)
        if kind:  # 크레딧이 드는 요청만 센다. 날이 바뀌면 처음부터
            today = time.strftime("%Y-%m-%d")
            if JUDGE_USE["day"] != today:
                JUDGE_USE.update(day=today, n={})
            if JUDGE_USE["n"].get(kind, 0) >= JUDGE_LIMITS[kind]:
                return JSONResponse({"error": "daily limit for the judge key"}, 429)
            JUDGE_USE["n"][kind] = JUDGE_USE["n"].get(kind, 0) + 1
            save_state()
    request.state.who = role
    if m and not use_only and (RUNS / m.group(1)).is_dir():  # 누가 무엇을 바꿨는지(따라 하기 판단은 너무 잦아서 뺀다)
        with (RUNS / m.group(1) / "audit.jsonl").open("a") as f:
            f.write(json.dumps({"t": round(time.time()), "who": role, "do": f"{request.method} {path[len(m.group(0)):] or '/'}"}, ensure_ascii=False) + "\n")
    return await call_next(request)


CARDS_LOCK = threading.Lock()  # cards.json 읽고-고치고-쓰기가 동시에 겹치지 않게
RUNNING, RUNNING_LOCK = set(), threading.Lock()  # 파이프라인이 도는 실행 id: 같은 영상을 또 올려도 두 번 돌리지 않게
CARD_PATH = re.compile(r"cards/[\w.-]+\.(jpg|png)")
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")  # 결과 폴더만 공개(리포 전체 X)


def run_dir(run_id):
    d = RUNS / run_id
    if not run_id.isalnum() or not d.is_dir():
        raise HTTPException(404, "없는 실행입니다")
    return d


def read(d, name, default=None):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default


def inside(d, rel):
    """카드에 적힌 파일 경로가 실행 폴더 안인지 확인하고 실제 경로를 준다"""
    p = (d / rel).resolve()
    if not p.is_relative_to(d.resolve()):
        raise HTTPException(400, "잘못된 파일 경로입니다")
    return p


def card_list(d):
    data = read(d, "cards.json")
    if data is None:
        raise HTTPException(404, "아직 카드가 없습니다")
    return data["cards"]


def atomic(out, make):
    """make(임시 경로)로 같은 폴더에 쓴 뒤 바꿔 끼운다: 동시 요청이 반쪽 파일을 받거나 실패한 파일이 남지 않게"""
    out.parent.mkdir(exist_ok=True)
    tmp = out.with_name(f".{uuid.uuid4().hex}_{out.name}")
    try:
        make(tmp)
        os.replace(tmp, out)
    finally:
        tmp.unlink(missing_ok=True)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/runs")
def runs(request: Request):
    """처음 화면 목록. 키가 없으면 견본만: 교사가 올린 카드 묶음은 주소(추측하기 어려운 id)를 아는 사람만 연다"""
    out, role = [], who(request)
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        prog = read(d, "progress.json") if d.is_dir() else None
        if prog and (role == "admin" or d.name in SEED_INDEX or (role and owner_of(d.name) == role)):
            data = read(d, "cards.json")
            cs = data["cards"] if data else []
            seed = SEED_INDEX.get(d.name, {})
            out.append({"id": d.name, "video": prog["video"], "title": (data or {}).get("title") or seed.get("title", ""), "title_en": seed.get("title_en", ""), "use": seed.get("use", ""),
                        "done": data is not None, "count": len(cs),
                        "issues": len(data["problems"]) if data else 0, "thumb": cs[0]["image"] if cs else None,
                        "stage": storage.stage(d), "delete_on": None if d.name in SEED_INDEX else storage.delete_on(d)})
    return out


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    """카드 묶음 지우기: 실행 폴더와, 올린 영상이 업로드 폴더에 있으면 그것도"""
    d = run_dir(run_id)
    with RUNNING_LOCK:
        if run_id in RUNNING:
            raise HTTPException(409, "아직 만드는 중입니다")
    video = Path((read(d, "progress.json") or {}).get("video_path") or "")
    shutil.rmtree(d)
    if video.is_file() and video.resolve().parent == UPLOADS.resolve():
        video.unlink()
    NOW.pop(run_id, None)
    return {"ok": True}


MAX_UPLOAD_MB, MAX_VIDEO_SEC, MIN_FREE_GB = 500, 600, 2


def video_seconds(path):
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile, local: bool = Form(False)):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    tmp, h = UPLOADS / f".{uuid.uuid4().hex}.part", hashlib.sha256()
    try:  # 이름이 같은 다른 영상이 옛 영상을 덮지 않게 내용 해시를 이름 앞에 붙인다
        size = 0
        with tmp.open("wb") as f:
            while b := file.file.read(1 << 20):
                size += len(b)
                if size > MAX_UPLOAD_MB << 20:
                    raise HTTPException(413, f"영상이 너무 큽니다({MAX_UPLOAD_MB}MB 이하)")
                h.update(b)
                f.write(b)
        if shutil.disk_usage(UPLOADS).free < MIN_FREE_GB << 30:
            raise HTTPException(507, "저장 공간이 부족합니다")
        secs = video_seconds(tmp)
        if not 0 < secs <= MAX_VIDEO_SEC:
            raise HTTPException(400, f"영상 길이는 {MAX_VIDEO_SEC // 60}분 이하여야 합니다" if secs else "영상을 읽지 못했습니다")
        dest = UPLOADS / f"{h.hexdigest()[:12]}_{Path(file.filename).name}"
        if not dest.exists():
            os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    role = getattr(request.state, "who", "admin")
    if role != "admin":  # 교사(심사) 한 사람이 저장소를 다 쓰지 않게
        n, used = storage.owned_usage(RUNS, UPLOADS, role)
        if n >= storage.TEACHER_MAX_SETS or used + dest.stat().st_size > storage.TEACHER_QUOTA_MB << 20:
            raise HTTPException(403, f"저장 한도({storage.TEACHER_MAX_SETS}묶음·{storage.TEACHER_QUOTA_MB}MB)를 넘었습니다")
    run = pipeline.Run(dest)
    if not (run.dir / "owner.txt").exists():  # 처음 올린 사람이 주인(교사 키는 자기 것만 고친다)
        (run.dir / "owner.txt").write_text(getattr(request.state, "who", "admin"))
    if not local and not pipeline.API_KEY:
        raise HTTPException(503, "Meta API 키가 없어 이 맥에서 만들기만 됩니다")
    if local and not coach.local_ready():
        raise HTTPException(409, "이 맥의 Muse Glimmer 서버가 켜져 있지 않습니다")
    if not any(e.get("stage") == "done" for e in run.events):  # 이미 끝난 실행은 다시 돌리지 않는다
        start(run.dir.name, dest, local)
    return {"id": run.dir.name}


def start(run_id, video, local=False):
    """카드 만들기를 뒤에서 돌린다. 같은 실행이 이미 돌고 있으면 False"""
    with RUNNING_LOCK:
        if run_id in RUNNING:
            return False
        RUNNING.add(run_id)

    def go():
        try:
            pipeline.main(video, local=local)
        finally:
            with RUNNING_LOCK:
                RUNNING.discard(run_id)
    threading.Thread(target=go, daemon=True).start()
    return True


@app.post("/api/runs/{run_id}/agent")
def teacher_agent(run_id: str, body: dict):
    """교사 부탁 → Muse Spark가 검사기를 도구로 써 가며 문장 고칠 안을 만든다. 저장은 하지 않는다(교사가 적용)."""
    import agent
    d = run_dir(run_id)
    data = read(d, "cards.json")
    instruction = str(body.get("instruction", "")).strip()[:300]
    if not data or not instruction:
        raise HTTPException(400, "부탁할 내용이 없습니다")
    return agent.run(data["cards"], data.get("duration", len(list((d / "frames").glob("*.jpg")))), instruction)


@app.post("/api/runs/{run_id}/retry")
def retry(run_id: str):
    """멈춘 실행을 같은 영상으로 다시 돌린다(영상을 다시 올리지 않아도 되게)"""
    d = run_dir(run_id)
    video = Path((read(d, "progress.json") or {}).get("video_path") or "")
    if not video.is_file():
        raise HTTPException(404, "영상 파일이 없습니다")
    prog = read(d, "progress.json") or {}
    local = any(e.get("stage") == "start" and e.get("local") for e in prog.get("events", []))  # 처음 고른 곳(이 맥/API) 그대로
    if not start(run_id, video, local):
        raise HTTPException(409, "아직 만드는 중입니다")
    return {"id": run_id}


@app.get("/api/runs/{run_id}/progress")
def progress(run_id: str):
    d = run_dir(run_id)
    p = read(d, "progress.json", {"events": []})
    p["title"] = (read(d, "cards.json") or {}).get("title") or SEED_INDEX.get(run_id, {}).get("title", "")  # 진행 화면에 파일 이름 대신
    return p


@app.get("/api/runs/{run_id}/cards")
def cards(run_id: str):
    d = run_dir(run_id)
    data = read(d, "cards.json")
    if data is None:
        raise HTTPException(404, "아직 카드가 없습니다")
    # 검사기가 첫 답에서 잡아 다시 만들게 한 것(화면에 보여 준다). 견본은 영어 제목도
    splits = [e for e in (read(d, "progress.json") or {}).get("events", []) if e.get("stage") == "split" and "n" in e]
    caught = splits[0]["problems"] if len(splits) > 1 and splits[0].get("problems") else []
    storage.touch_used(d)
    vk = voice.kinds(d, data["cards"])
    data = {**data, "cards": [{**c, "voice": vk.get(c["n"])} for c in data["cards"]]}
    return {**data, "caught": caught, "tries": len(splits), "title_en": SEED_INDEX.get(run_id, {}).get("title_en", ""),
            "stage": storage.stage(d), "delete_on": storage.delete_on(d) if run_id not in SEED_INDEX else None}


@app.put("/api/runs/{run_id}/cards")
def save(run_id: str, body: dict):
    d = run_dir(run_id)
    with CARDS_LOCK:
        return _save(d, body)


def _save(d, body):
    data = read(d, "cards.json")
    for c in body["cards"]:  # 사진·그림 경로는 실행 폴더의 cards/ 안 파일만
        for k in ("image", "ill"):
            if c.get(k) is not None and not (isinstance(c[k], str) and CARD_PATH.fullmatch(c[k])):
                raise HTTPException(400, f"잘못된 파일 경로입니다: {k}")
    data["cards"] = body["cards"]
    if isinstance(body.get("title"), str):
        data["title"] = body["title"].strip()[:60]
    data["problems"], data["warnings"] = check(data["cards"], data.get("duration", len(list((d / "frames").glob("*.jpg")))))
    data["status"] = "ok" if not data["problems"] else "needs_review"
    data["edited_at"] = time.time()
    (d / "cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data


@app.post("/api/runs/{run_id}/cards/{n}/frame")
def reframe(run_id: str, n: int, t: int):
    """n번 카드 사진을 t초 장면으로 바꾸고 강조 상자를 다시 찾는다."""
    d = run_dir(run_id)
    if storage.stage(d) == "archived":
        raise HTTPException(409, "보관된 카드 묶음이라 영상이 없습니다")
    card = next((c for c in card_list(d) if c["n"] == n), None)
    if card is None:
        raise HTTPException(404, "없는 카드입니다")
    img, hl = inside(d, card["image"]), inside(d, card["image"].replace(".jpg", "_hl.jpg"))
    pipeline.grab(read(d, "progress.json")["video_path"], t, img)  # 오래 걸리는 부분은 잠그지 않음
    box, used, touch = pipeline.find_box(img, card)
    hl.unlink(missing_ok=True)
    if box:
        pic = Image.open(img).convert("RGB")
        ImageDraw.Draw(pic).rectangle(box, outline=(255, 140, 0), width=6)
        pic.save(hl, quality=85)
    with CARDS_LOCK:  # 그사이 저장된 편집을 잃지 않게 다시 읽고 이 카드만 고친다
        data = read(d, "cards.json")
        card = next((c for c in data["cards"] if c["n"] == n), None)
        if card is None:
            raise HTTPException(404, "없는 카드입니다")
        if card.get("ill"):  # 그림은 옛 사진 기준이라 지운다
            inside(d, card["ill"]).unlink(missing_ok=True)
        card.pop("ill", None)
        card["view"] = "photo"
        card.update(frame_t=t, rep=t, box=box, box_prompt=used, box_touches_hand=touch)
        (d / "cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return card


@app.post("/api/runs/{run_id}/cards/{n}/illustrate")
def illustrate(run_id: str, n: int):
    """n번 카드 사진을 그림 카드로(Muse Image). 교사가 사진·그림 중 고른다."""
    d = run_dir(run_id)
    data = read(d, "cards.json")
    card = next((c for c in data["cards"] if c["n"] == n), None)
    if card is None:
        raise HTTPException(404, "없는 카드입니다")
    rel = card["image"].replace(".jpg", "_ill.jpg")
    inside(d, rel).write_bytes(pipeline.illustrate(inside(d, card["image"]), card.get("object", "")))  # 오래 걸리는 부분은 잠그지 않음
    with CARDS_LOCK:
        data = read(d, "cards.json")
        card = next((c for c in data["cards"] if c["n"] == n), None)
        if card is None:
            raise HTTPException(404, "없는 카드입니다")
        card.update(ill=rel, view="ill")
        (d / "cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return card


@app.post("/api/runs/{run_id}/coach")
def coach_check(run_id: str, body: dict):
    """따라 하기: 카메라 사진 몇 장으로 카드를 넘길지 정한다. 사진은 저장하지 않는다."""
    data = read(run_dir(run_id), "cards.json")
    frames = [f for f in body.get("frames", [])[-6:] if isinstance(f, str) and f.startswith("data:image/jpeg;base64,")]
    cur = int(body.get("cur", 1))
    if len(frames) < 2 or not 1 <= cur <= len(data["cards"]):
        raise HTTPException(400, "사진이 부족하거나 카드 번호가 틀렸습니다")
    ref = None
    if body.get("live"):  # 실시간 확인: 지금 카드의 완료 기준 사진을 같은 판단에 넣는다
        d = run_dir(run_id)
        ref = pipeline.data_url(verify.reference(d, data["cards"][cur - 1], "after"))
    return coach.check(data["cards"], cur, frames, int(body.get("prev_seen") or 0), bool(body.get("local")), ref)


# 안경 화면(Ray-Ban Display 웹앱)과 따라 하기 화면이 같은 카드를 보게 하는 공유 상태. 메모리에만 둔다


@app.get("/glasses")
def glasses():
    return FileResponse(ROOT / "static" / "glasses.html")


@app.get("/api/runs/{run_id}/now")
def now_get(run_id: str, s: str = ""):
    return NOW.get(now_key(run_id, s), {"i": 0, "again": False, "by": "", "v": 0, "lv": 0})


def now_key(run_id, s):
    """같은 카드 묶음을 여러 학생이 동시에 쓰면 따라 하기 화면마다 짝 코드(s)로 나눈다. 없으면 카드 묶음 하나에 하나"""
    s = re.sub(r"[^a-z0-9]", "", str(s).lower())[:8]
    return f"{run_id}|{s}" if s else run_id


@app.post("/api/runs/{run_id}/now")
def now_set(run_id: str, body: dict):
    n = len(read(run_dir(run_id), "cards.json")["cards"])
    key = now_key(run_id, body.get("s", ""))
    v = NOW.get(key, {}).get("v", 0) + 1
    NOW[key] = {"i": max(0, min(n - 1, int(body.get("i", 0)))), "again": bool(body.get("again")), "by": str(body.get("by", ""))[:10], "v": v,
                   "lv": max(0, min(4, int(body.get("lv") or 0))), "fin": bool(body.get("fin")), "t": round(time.time()),
                 # 안경 '확인' → 따라 하기 화면이 휴대폰 카메라로 찍어 확인(vreq), 결과를 안경에 돌려준다(vres)
                 "vreq": int(body.get("vreq") or 0), "vres": {k: str(v)[:80] for k, v in (body.get("vres") or {}).items()} if isinstance(body.get("vres"), dict) else None}  # fin = 마지막 단계까지 마침  # 도움 단계(0=끔, 1 글 → 4 움직임)
    save_state()
    return NOW[key]


@app.get("/api/runs/{run_id}/glass/{i}.jpg")
def glass_img(run_id: str, i: int, ill: int = 1):
    """안경 화면용 작은 사진(600x600 화면, 느린 연결이라 가로 520px JPEG로 줄인다)"""
    d = run_dir(run_id)
    cs = card_list(d)
    if not 0 <= i < len(cs):
        raise HTTPException(404, "없는 카드입니다")
    c = cs[i]
    src = c["ill"] if ill and c.get("view") == "ill" and c.get("ill") else (c["image"].replace(".jpg", "_hl.jpg") if c.get("box") and not c.get("hl_off") else c["image"])
    out = d / "glass" / f"{i}_{Path(src).stem}_{c.get('v') or 0}_k.jpg"
    if not out.exists():
        im = Image.open(inside(d, src)).convert("RGB")
        im.thumbnail((520, 520))
        if src == c.get("ill"):  # 렌즈에서 흰색은 가장 밝은 빛이라, 그림의 흰 바탕은 검게(투명), 검은 선은 밝게 바꾼다
            lum = im.convert("L")
            im.paste((0, 0, 0), mask=lum.point(lambda v: 255 if v > 232 else 0))
            im.paste((207, 211, 217), mask=lum.point(lambda v: 255 if v < 48 else 0))
        atomic(out, lambda tmp: im.save(tmp, "JPEG", quality=78))
    return FileResponse(out)


@app.get("/api/runs/{run_id}/clip/{n}.mp4")
def card_clip(run_id: str, n: int, g: int = 0):
    """n번 카드의 움직임(대표 장면 앞뒤 최대 4초). g=1 은 안경 화면용(한 변 400px·7만 화소 아래)"""
    d = run_dir(run_id)
    if storage.stage(d) == "archived":
        raise HTTPException(409, "보관된 카드 묶음이라 영상이 없습니다")
    c = next((c for c in card_list(d) if c["n"] == n), None)
    if c is None:
        raise HTTPException(404, "없는 카드입니다")
    dur = max(1, min(4, c["end"] - c["start"]))
    mid = c.get("frame_t", c.get("rep", c["start"]))
    t0 = max(c["start"], min(c["end"] - dur, mid - dur / 2))
    out = d / "clips" / f"{n}_{t0}_{dur}_{g}.mp4"
    if not out.exists():
        atomic(out, lambda tmp: pipeline.clip(read(d, "progress.json")["video_path"], t0, dur, tmp, 352 if g else 640))
    return FileResponse(out, media_type="video/mp4")


@app.get("/api/runs/{run_id}/qr.svg")
def qr(run_id: str, request: Request, to: str = "tablet", lang: str = "ko", s: str = ""):
    """학생 기기로 넘기는 QR: 태블릿 보기나 안경 화면 주소(보기는 키 없이 된다)"""
    import segno
    run_dir(run_id)
    base = f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"
    lang = lang if lang in ("ko", "en", "both") else "ko"
    url = f"{base}/glasses?run={run_id}&lang={lang}" + (f"&s={re.sub(r'[^a-z0-9]', '', s.lower())[:8]}" if s else "") if to == "glasses" else f"{base}/?ui={lang if lang != 'both' else 'ko'}#run={run_id}&view=tablet"
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#1c2b33")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


BACKUPS = DATA / "backups"


def maintenance_loop():
    """6시간마다 저장 공간 정리(storage.maintain): 소리 파일·캐시·정리·보관·삭제·기록·교사 자료 백업"""
    while True:
        try:
            did = storage.maintain(RUNS, UPLOADS, set(SEED_INDEX), BACKUPS, NOW, running=set(RUNNING))
            save_state()
            print("[maintain]", did, flush=True)
            du = shutil.disk_usage(RUNS)
            if du.used / du.total > 0.9:
                pipeline.alert(f"StepCards: 저장 공간 {du.used / du.total:.0%} 사용")
        except Exception as e:  # 정리가 실패해도 서버는 계속
            pipeline.alert(f"StepCards: 저장 공간 정리 실패 ({type(e).__name__})")
        time.sleep(6 * 3600)


if os.environ.get("MAINTENANCE", "1") == "1":
    threading.Thread(target=maintenance_loop, daemon=True).start()


def admin_only(request):
    if who(request) != "admin":
        raise HTTPException(403, "관리자 키가 필요합니다")


@app.get("/api/admin/storage")
def admin_storage(request: Request):
    """관리자 화면: 카드 묶음마다 크기·주인·단계·마지막 사용, 교사별 합계, 전체"""
    admin_only(request)
    rows = []
    for d in sorted(RUNS.iterdir()):
        if d.is_dir() and (d / "progress.json").exists():
            data = read(d, "cards.json") or {}
            rows.append({"id": d.name, "title": data.get("title") or SEED_INDEX.get(d.name, {}).get("title") or storage.progress(d).get("video", ""),
                         "owner": owner_of(d.name) or ("seed" if d.name in SEED_INDEX else "admin"), "stage": storage.stage(d),
                         "last_used": storage.last_used(d), "delete_on": storage.delete_on(d), "size": storage.report(d, UPLOADS)})
    du = shutil.disk_usage(RUNS)
    owners = {}
    for r in rows:
        o = owners.setdefault(r["owner"], {"sets": 0, "bytes": 0}); o["sets"] += 1; o["bytes"] += r["size"]["total"]
    return {"runs": rows, "owners": owners, "free": du.free, "total": du.total,
            "policy": {"compact_days": storage.COMPACT_DAYS, "archive_days": storage.ARCHIVE_DAYS, "retain_days": storage.RETAIN_DAYS,
                       "quota_mb": storage.TEACHER_QUOTA_MB, "max_sets": storage.TEACHER_MAX_SETS},
            "backups": [f.name for f in sorted(BACKUPS.glob("teacher-*.zip"))]}


@app.post("/api/admin/runs/{run_id}/{action}")
def admin_action(run_id: str, action: str, request: Request):
    admin_only(request)
    d = run_dir(run_id)
    if run_id in SEED_INDEX or action not in ("compact", "archive"):
        raise HTTPException(400, "견본이거나 모르는 동작입니다")
    ok = (storage.compact if action == "compact" else storage.archive)(d, RUNS, UPLOADS)
    return {"ok": ok, "stage": storage.stage(d)}


@app.get("/api/admin/backup.zip")
def admin_backup(request: Request):
    admin_only(request)
    return FileResponse(storage.backup(RUNS, BACKUPS, set(SEED_INDEX)), media_type="application/zip", filename="stepcards-teacher-backup.zip")


@app.post("/api/runs/{run_id}/frames")
def frames(run_id: str):
    """정리된 카드 묶음에서 장면 고르기를 열면 1초 사진을 다시 뽑는다"""
    d = run_dir(run_id)
    if storage.stage(d) == "archived":
        raise HTTPException(409, "보관된 카드 묶음입니다")
    return {"ok": storage.ensure_frames(d)}


def card_by_n(d, n):
    c = next((c for c in card_list(d) if c["n"] == n), None)
    if c is None:
        raise HTTPException(404, "없는 카드입니다")
    return c


@app.post("/api/runs/{run_id}/cards/{n}/verify")
def verify_card(run_id: str, n: int, body: dict):
    """확인하기: 학생 사진 한 장을 그 카드의 완료 기준과 비교. 사진은 저장하지 않는다"""
    d = run_dir(run_id)
    c = card_by_n(d, n)
    photo = body.get("photo", "")
    if not (isinstance(photo, str) and photo.startswith("data:image/jpeg;base64,")) or len(photo) > 3_000_000:
        raise HTTPException(400, "사진이 없거나 너무 큽니다")
    before, after = (pipeline.data_url(verify.reference(d, c, w)) for w in ("before", "after"))
    t0 = time.time()
    ans, cost = verify.ask(c, before, after, photo, bool(body.get("local")))
    out = {**verify.tidy(ans, c), "latency": round(time.time() - t0, 2), "cost": round(cost, 4)}
    if body.get("record"):
        add_record(d, {"kind": "verify", "n": n, "result": out["result"], "lv": int(body.get("lv") or 0), "s": str(body.get("s", ""))[:8]})
    return out


@app.get("/api/runs/{run_id}/voice/{n}")
def card_voice(run_id: str, n: int):
    """카드의 사람 목소리: 교사 녹음 → 영상 속 그 단계 말소리. 없으면 404(화면이 기기 음성으로 읽는다)"""
    d = run_dir(run_id)
    c = card_by_n(d, n)
    f = voice.recorded(d, n) or voice.cut(d, c)
    if not f:
        raise HTTPException(404, "목소리가 없습니다")
    return FileResponse(f, media_type={"webm": "audio/webm", "m4a": "audio/mp4", "ogg": "audio/ogg", "mp3": "audio/mpeg"}[f.suffix[1:]],
                        headers={"Cache-Control": "no-cache"})


@app.post("/api/runs/{run_id}/cards/{n}/voice")
async def record_voice(run_id: str, n: int, file: UploadFile):
    """교사가 카드 문장을 직접 녹음(고치기 화면)"""
    d = run_dir(run_id)
    card_by_n(d, n)
    ext = voice.REC_TYPES.get((file.content_type or "").split(";")[0])
    data = await file.read(voice.REC_MAX_BYTES + 1)
    if not ext or not data or len(data) > voice.REC_MAX_BYTES:
        raise HTTPException(400, "녹음 파일 형식이나 크기가 맞지 않습니다")
    (d / "voice").mkdir(exist_ok=True)
    old = voice.recorded(d, n)
    if old:
        old.unlink()
    (d / "voice" / f"{n:02d}_rec.{ext}").write_bytes(data)
    return {"ok": True, "voice": "rec"}


@app.delete("/api/runs/{run_id}/cards/{n}/voice")
def delete_voice(run_id: str, n: int):
    d = run_dir(run_id)
    old = voice.recorded(d, n)
    if old:
        old.unlink()
    c = card_by_n(d, n)
    return {"ok": True, "voice": voice.kinds(d, [c]).get(n)}


@app.get("/api/runs/{run_id}/cards/{n}/after.jpg")
def card_after(run_id: str, n: int):
    """완료 기준 사진(시범 영상에서 그 단계가 끝난 순간)"""
    d = run_dir(run_id)
    return FileResponse(inside(d, str(verify.reference(d, card_by_n(d, n), "after").relative_to(d))))


def add_record(d, row):
    """교사가 '기록 남기기'를 켰을 때만: 이름 없이 날짜·카드·결과·도움 단계"""
    with (d / "records.jsonl").open("a") as f:
        f.write(json.dumps({"t": round(time.time()), **row}, ensure_ascii=False) + "\n")


@app.post("/api/runs/{run_id}/records")
def post_records(run_id: str, body: dict):
    """따라 하기 끝 화면의 카드별 도움 단계(기록 켰을 때)"""
    d = run_dir(run_id)
    for r in (body.get("rows") or [])[:200]:
        add_record(d, {"kind": "coach", "n": int(r.get("n", 0)), "lv": int(r.get("lv", 0)), "s": str(body.get("s", ""))[:8]})
    return {"ok": True}


@app.get("/api/runs/{run_id}/records")
def get_records(run_id: str, request: Request):
    """학습 기록은 키가 있는 사람만(보기 공개와 달리)"""
    if not has_key(request):
        raise HTTPException(401, "key required")
    f = run_dir(run_id) / "records.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


@app.get("/api/health")
def health():
    """상태 점검(Railway healthcheck·바깥 감시용): 저장 공간, 도는 작업, 키 여부"""
    du = shutil.disk_usage(RUNS)
    return {"ok": du.free > MIN_FREE_GB << 30 and du.used / du.total < 0.9, "free_gb": round(du.free / 2**30, 1), "used_pct": round(du.used / du.total * 100),
            "card_sets": sum(1 for d in RUNS.iterdir() if d.is_dir()), "making": len(RUNNING), "api_key": bool(pipeline.API_KEY)}


@app.get("/api/runs/{run_id}/export.zip")
def export(run_id: str):
    """카드 묶음 내려받기(백업·다른 서버로 옮기기): 카드·사진·그림·제목. 영상과 1초 사진은 빼서 작게"""
    import zipfile
    d = run_dir(run_id)
    if not (d / "cards.json").exists():
        raise HTTPException(404, "아직 카드가 없습니다")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(d / "cards.json", "cards.json")
        for f in sorted((d / "cards").glob("*")):
            z.write(f, f"cards/{f.name}")
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="stepcards_{run_id}.zip"'})


@app.exception_handler(Exception)
async def crashed(request: Request, e: Exception):  # 처리 못 한 오류는 알림으로(무엇이 터졌는지만, 내용은 로그에)
    pipeline.alert(f"StepCards: 서버 오류 {request.method} {request.url.path} ({type(e).__name__})")
    return JSONResponse({"error": "server error"}, 500)


@app.get("/api/local")
def local_status():
    """이 맥에 Muse Glimmer 서버가 떠 있는지(만들기·따라 하기 선택지에 씀)와 Meta API 키가 있는지"""
    return {"ready": coach.local_ready(), "api": bool(pipeline.API_KEY)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8790)))
