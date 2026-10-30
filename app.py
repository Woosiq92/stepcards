# 로컬 서버: 영상 올리기 → 파이프라인 → 진행판·편집·인쇄·태블릿 보기
# 사용: .venv/bin/python app.py  → http://127.0.0.1:8790
import hashlib, hmac, io, json, os, re, shutil, threading, time, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
import coach
import pipeline
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
        if f.is_file() and not (RUNS / s.name / f.relative_to(s)).exists():
            (RUNS / s.name / f.relative_to(s)).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, RUNS / s.name / f.relative_to(s))
    if new:
        p = json.loads((RUNS / s.name / "progress.json").read_text())
        p["video_path"] = str(RUNS / s.name / "video.mp4")
        (RUNS / s.name / "progress.json").write_text(json.dumps(p, ensure_ascii=False))
APP_KEY = os.environ.get("APP_KEY", "")  # 공개 주소에 올릴 때만 설정: 키를 아는 사람만 크레딧을 쓰고 카드를 바꾸게
NOW_PATH = re.compile(r"/api/runs/\w+/now$")
app = FastAPI()


@app.middleware("http")
async def need_key(request: Request, call_next):
    """보기(GET)는 누구나. 돈이 들거나 데이터를 바꾸는 요청만 접속 키(쿠키)가 있어야 한다.
    키는 화면 안 입력 칸에서 POST /login 으로 받는다. 안경·따라 하기의 지금 카드 맞추기(/now)는 키 없이"""
    if not APP_KEY or request.method in ("GET", "HEAD") or NOW_PATH.match(request.url.path):
        return await call_next(request)
    if request.url.path == "/login" and request.method == "POST":
        k = str((await request.form()).get("k", ""))
        if not hmac.compare_digest(k.encode(), APP_KEY.encode()):
            return JSONResponse({"error": "wrong key"}, 401)
        r = JSONResponse({"ok": True})
        r.set_cookie("sc_key", APP_KEY, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax")
        return r
    if hmac.compare_digest(request.cookies.get("sc_key", "").encode(), APP_KEY.encode()):
        return await call_next(request)
    return JSONResponse({"error": "key required"}, 401)
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
def runs():
    out = []
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        prog = read(d, "progress.json") if d.is_dir() else None
        if prog:
            data = read(d, "cards.json")
            cs = data["cards"] if data else []
            seed = SEED_INDEX.get(d.name, {})
            out.append({"id": d.name, "video": prog["video"], "title": (data or {}).get("title") or seed.get("title", ""), "title_en": seed.get("title_en", ""), "use": seed.get("use", ""),
                        "done": data is not None, "count": len(cs),
                        "issues": len(data["problems"]) if data else 0, "thumb": cs[0]["image"] if cs else None})
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


@app.post("/api/upload")
async def upload(file: UploadFile):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    tmp, h = UPLOADS / f".{uuid.uuid4().hex}.part", hashlib.sha256()
    try:  # 이름이 같은 다른 영상이 옛 영상을 덮지 않게 내용 해시를 이름 앞에 붙인다
        with tmp.open("wb") as f:
            while b := file.file.read(1 << 20):
                h.update(b)
                f.write(b)
        dest = UPLOADS / f"{h.hexdigest()[:12]}_{Path(file.filename).name}"
        if not dest.exists():
            os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    run = pipeline.Run(dest)
    if not any(e.get("stage") == "done" for e in run.events):  # 이미 끝난 실행은 다시 돌리지 않는다
        start(run.dir.name, dest)
    return {"id": run.dir.name}


def start(run_id, video):
    """카드 만들기를 뒤에서 돌린다. 같은 실행이 이미 돌고 있으면 False"""
    with RUNNING_LOCK:
        if run_id in RUNNING:
            return False
        RUNNING.add(run_id)

    def go():
        try:
            pipeline.main(video)
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
    if not start(run_id, video):
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
    data = read(run_dir(run_id), "cards.json")
    if data is None:
        raise HTTPException(404, "아직 카드가 없습니다")
    return data


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
    return coach.check(data["cards"], cur, frames, int(body.get("prev_seen") or 0), bool(body.get("local")))


# 안경 화면(Ray-Ban Display 웹앱)과 따라 하기 화면이 같은 카드를 보게 하는 공유 상태. 메모리에만 둔다
NOW = {}


@app.get("/glasses")
def glasses():
    return FileResponse(ROOT / "static" / "glasses.html")


@app.get("/api/runs/{run_id}/now")
def now_get(run_id: str):
    return NOW.get(run_id, {"i": 0, "again": False, "by": "", "v": 0, "lv": 0})


@app.post("/api/runs/{run_id}/now")
def now_set(run_id: str, body: dict):
    n = len(read(run_dir(run_id), "cards.json")["cards"])
    v = NOW.get(run_id, {}).get("v", 0) + 1
    NOW[run_id] = {"i": max(0, min(n - 1, int(body.get("i", 0)))), "again": bool(body.get("again")), "by": str(body.get("by", ""))[:10], "v": v,
                   "lv": max(0, min(4, int(body.get("lv") or 0))), "fin": bool(body.get("fin"))}  # fin = 마지막 단계까지 마침  # 도움 단계(0=끔, 1 글 → 4 움직임)
    return NOW[run_id]


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
def qr(run_id: str, request: Request, to: str = "tablet", lang: str = "ko"):
    """학생 기기로 넘기는 QR: 태블릿 보기나 안경 화면 주소(보기는 키 없이 된다)"""
    import segno
    run_dir(run_id)
    base = f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"
    lang = lang if lang in ("ko", "en", "both") else "ko"
    url = f"{base}/glasses?run={run_id}&lang={lang}" if to == "glasses" else f"{base}/?ui={lang if lang != 'both' else 'ko'}#run={run_id}&view=tablet"
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#1c2b33")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/local")
def local_status():
    """이 맥에 Muse Glimmer 서버가 떠 있는지(따라 하기 선택지에 씀)"""
    return {"ready": coach.local_ready()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8790)))
