# 로컬 서버: 영상 올리기 → 파이프라인 → 진행판·편집·인쇄·태블릿 보기
# 사용: .venv/bin/python app.py  → http://127.0.0.1:8790
import json, shutil, threading, time
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw
import pipeline
from check import check

ROOT = Path(__file__).parent
RUNS = ROOT / "runs"
UPLOADS = ROOT / "samples" / "uploads"
app = FastAPI()
app.mount("/runs", StaticFiles(directory=RUNS), name="runs")  # 결과 폴더만 공개(리포 전체 X)
BRAND = ROOT / "static" / "brand"  # 기관 로고(리포에 올리지 않음). 없으면 화면에서 숨김
BRAND.mkdir(parents=True, exist_ok=True)
app.mount("/brand", StaticFiles(directory=BRAND), name="brand")


def run_dir(run_id):
    d = RUNS / run_id
    if not run_id.isalnum() or not d.is_dir():
        raise HTTPException(404, "없는 실행입니다")
    return d


def read(d, name, default=None):
    p = d / name
    return json.loads(p.read_text()) if p.exists() else default


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
            out.append({"id": d.name, "video": prog["video"], "done": data is not None, "count": len(cs),
                        "issues": len(data["problems"]) if data else 0, "thumb": cs[0]["image"] if cs else None})
    return out


@app.post("/api/upload")
async def upload(file: UploadFile):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / Path(file.filename).name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    run_id = pipeline.Run(dest).dir.name
    threading.Thread(target=pipeline.main, args=(dest,), daemon=True).start()
    return {"id": run_id}


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
    data = read(d, "cards.json")
    data["cards"] = body["cards"]
    data["problems"], data["warnings"] = check(data["cards"], data.get("duration", len(list((d / "frames").glob("*.jpg")))))
    data["status"] = "ok" if not data["problems"] else "needs_review"
    data["edited_at"] = time.time()
    (d / "cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data


@app.post("/api/runs/{run_id}/cards/{n}/frame")
def reframe(run_id: str, n: int, t: int):
    """n번 카드 사진을 t초 장면으로 바꾸고 강조 상자를 다시 찾는다."""
    d = run_dir(run_id)
    data = read(d, "cards.json")
    card = next((c for c in data["cards"] if c["n"] == n), None)
    if card is None:
        raise HTTPException(404, "없는 카드입니다")
    img = d / card["image"]
    pipeline.grab(read(d, "progress.json")["video_path"], t, img)
    box, used, touch = pipeline.find_box(img, card)
    hl = d / card["image"].replace(".jpg", "_hl.jpg")
    hl.unlink(missing_ok=True)
    if box:
        pic = Image.open(img).convert("RGB")
        ImageDraw.Draw(pic).rectangle(box, outline=(255, 140, 0), width=6)
        pic.save(hl, quality=85)
    card.update(frame_t=t, rep=t, box=box, box_prompt=used, box_touches_hand=touch)
    (d / "cards.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return card


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8790)
