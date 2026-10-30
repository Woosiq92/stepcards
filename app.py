# 로컬 서버: 영상 올리기 → 파이프라인 → 진행판·편집·인쇄·태블릿 보기
# 사용: .venv/bin/python app.py  → http://127.0.0.1:8790
import hashlib, hmac, json, os, re, shutil, threading, time, uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
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
for s in sorted(SEED.iterdir()) if SEED.is_dir() else []:
    if s.is_dir() and not (RUNS / s.name).exists():
        shutil.copytree(s, RUNS / s.name)
        p = json.loads((RUNS / s.name / "progress.json").read_text())
        p["video_path"] = str(RUNS / s.name / "video.mp4")
        (RUNS / s.name / "progress.json").write_text(json.dumps(p, ensure_ascii=False))
APP_KEY = os.environ.get("APP_KEY", "")  # 공개 주소에 올릴 때만 설정: 아는 사람만 들어와 크레딧을 쓰게
app = FastAPI()


@app.middleware("http")
async def need_key(request: Request, call_next):
    if not APP_KEY:
        return await call_next(request)
    k = request.query_params.get("k")
    if request.url.path == "/login" and request.method == "POST":  # 접속 키 입력 칸
        k = (await request.form()).get("k", "")
    if k is not None and hmac.compare_digest(k.encode(), APP_KEY.encode()):  # 주소에 한 번 붙여 오면 쿠키로 바꾸고 주소에서는 지운다
        q = "&".join(f"{a}={b}" for a, b in request.query_params.multi_items() if a != "k")
        r = RedirectResponse(("/" if request.url.path == "/login" else request.url.path) + (f"?{q}" if q else ""), 303)
        r.set_cookie("sc_key", APP_KEY, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax")
        return r
    if hmac.compare_digest(request.cookies.get("sc_key", "").encode(), APP_KEY.encode()):
        return await call_next(request)
    if request.url.path.startswith(("/api/", "/runs/")):
        return HTMLResponse("key required", 401)
    return HTMLResponse(KEY_PAGE, 401)


KEY_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>StepCards</title>
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#f1f4f7;font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;color:#1c2b33">
<form method="post" action="/login" style="background:#fff;padding:28px;border-radius:24px;box-shadow:0 4px 12px rgba(28,43,51,.08);display:grid;gap:12px;width:min(340px,90vw)">
<b style="font-size:20px">StepCards</b><span style="color:#65788a;font-size:14px">접속 키를 넣어 주세요 · Enter the access key</span>
<input name="k" type="password" autofocus style="padding:12px;border:1px solid #cbd2d9;border-radius:12px;font:inherit">
<button style="padding:12px;border:0;border-radius:999px;background:#0064e0;color:#fff;font:inherit;font-weight:600">들어가기 · Enter</button></form>"""
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
            out.append({"id": d.name, "video": prog["video"], "title": (data or {}).get("title", ""), "done": data is not None, "count": len(cs),
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
    with RUNNING_LOCK:  # 도는 중이거나 이미 끝난 실행은 다시 돌리지 않는다
        if run.dir.name in RUNNING or any(e.get("stage") == "done" for e in run.events):
            return {"id": run.dir.name}
        RUNNING.add(run.dir.name)

    def go():
        try:
            pipeline.main(dest)
        finally:
            with RUNNING_LOCK:
                RUNNING.discard(run.dir.name)
    threading.Thread(target=go, daemon=True).start()
    return {"id": run.dir.name}


@app.get("/api/runs/{run_id}/progress")
def progress(run_id: str):
    return read(run_dir(run_id), "progress.json", {"events": []})


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
    out = d / "glass" / f"{i}_{Path(src).stem}_{c.get('v') or 0}.jpg"
    if not out.exists():
        im = Image.open(inside(d, src)).convert("RGB")
        im.thumbnail((520, 520))
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


@app.get("/api/local")
def local_status():
    """이 맥에 Muse Glimmer 서버가 떠 있는지(따라 하기 선택지에 씀)"""
    return {"ready": coach.local_ready()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8790)))
