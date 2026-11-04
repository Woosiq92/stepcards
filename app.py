# 로컬 서버: 영상 올리기 → 파이프라인 → 진행판·편집·인쇄·태블릿 보기
# 사용: .venv/bin/python app.py  → http://127.0.0.1:8790
import hashlib, hmac, io, json, os, re, secrets, shutil, subprocess, threading, time, uuid
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, ImageDraw
import coach
import pipeline
import spend
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
    cj = RUNS / s.name / "cards.json"
    bump = cj.exists() and json.loads((s / "cards.json").read_text()).get("seed_v") != json.loads(cj.read_text()).get("seed_v")  # 견본 판이 바뀌면 카드와 사진을 모두 새 판으로(11-03: 사진은 이름이 같아 옛것이 남았다)
    for f in s.rglob("*"):  # 평소엔 빠진 파일만 채운다(교사가 고친 cards.json 은 그대로)
        dst = RUNS / s.name / f.relative_to(s)
        if f.is_file() and (not dst.exists() or bump or (f.name == "video.mp4" and dst.stat().st_size != f.stat().st_size)):
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
if not APP_KEY and any(k.startswith("RAILWAY_") for k in os.environ):  # 공개 배포(Railway)에서 키가 비면 전면 개방된다: 조용히 열지 말고 기동 거부(11-04 보안 검수)
    raise SystemExit("APP_KEY 가 비어 있습니다: 공개 배포에서는 전면 개방을 막기 위해 기동하지 않습니다. 환경변수 APP_KEY 를 설정하세요.")
JUDGE_KEY = os.environ.get("JUDGE_KEY", "")  # 심사위원용 키: 다 해 볼 수 있지만 하루 한도가 있다(제출 설명에 적는 키)
JUDGE_LIMITS = {"upload": 15, "illustrate": 60, "agent": 20, "translate": 10, "step": 400, "compare": 400, "coach": 3000, "frame": 60, "retry": 15, "verify": 600, "setup": 300}  # 하루 횟수, 심사위원 전원 합계(키가 하나라 사람을 못 가른다). 따라 하기 3000번 ≈ 2시간·약 $9. 전체는 비용 상한이 막는다
JUDGE_USE = {"day": "", "n": {}}
PUBLIC_LIMITS = {"coach": int(os.environ.get("PUBLIC_COACH_SET", 900)), "verify": int(os.environ.get("PUBLIC_VERIFY_SET", 300)), "records": 2000, "log": 2000}  # 키 없는 학습자 기기: 카드 묶음마다 하루(판단 약 $0.003·확인 약 $0.005 → 묶음당 하루 최대 약 $4)
PUBLIC_USE = {"day": "", "n": {}}
PUBLIC_TOTAL = {"coach": int(os.environ.get("PUBLIC_COACH_DAY", 3000)), "verify": int(os.environ.get("PUBLIC_VERIFY_DAY", 900))}  # 환경 변수로 바꿀 수 있다(코드 수정 없이 한 반 규모·심사 기간에 맞추게)  # 키 없는 기기 전체 하루 합계(견본 11개를 돌아가며 써도 하루 약 $14 안: 상한 $140 을 심사위원 몫으로 남긴다)
PAID_PATHS = ("/upload", "/retry", "/illustrate", "/agent", "/coach", "/verify", "/translate", "/step", "/compare", "/frame", "/setup")  # Meta 를 부르는 요청
TEACHERS = dict(x.strip().split(":", 1) for x in os.environ.get("TEACHER_KEYS", "").split(",") if ":" in x)  # 교사별 키 "이름:키,이름:키"
NOW_PATH = re.compile(r"/api/runs/\w+/(now|call|mark)$")  # 안경은 키(쿠키)가 없다: 지금 카드 맞추기와 '도와줘요'·'여기서 막혔어요'는 키 없이
MARKS = {}  # 혼자 하기 '여기서 막혔어요': 카드 묶음별 1분 안 횟수(장난 방지)
RUN_PATH = re.compile(r"/api/runs/(\w+)(?=/|$)")
STATE = DATA / "state.json"  # 안경·따라 하기 맞추기 상태와 심사용 키 사용량: 서버를 다시 켜도 이어지게


def load_state():
    try:
        st = json.loads(STATE.read_text())
        NOW.update(st.get("now", {})); JUDGE_USE.update(st.get("judge", {})); PUBLIC_USE.update(st.get("public", {}))
    except (OSError, ValueError):
        pass


STATE_LOCK = threading.Lock()


def save_state():
    with STATE_LOCK:  # 동시에 들어온 요청이 같은 임시 파일을 바꿔치기하다 500 이 났다(11-01 진단)
        tmp = STATE.with_suffix(f".{threading.get_ident()}.tmp")
        for k in [k for k, x in list(NOW.items()) if time.time() - x.get("t", 0) > 86400]:
            NOW.pop(k, None)
        snap = {k: dict(x) for k, x in list(NOW.items())}
        tmp.write_text(json.dumps({"now": snap, "judge": JUDGE_USE, "public": PUBLIC_USE}, ensure_ascii=False))
        os.replace(tmp, STATE)
NOW = {}
load_state()
app = FastAPI()


def eq(a, b):
    return bool(b) and hmac.compare_digest(a.encode(), b.encode())


def kst_day():
    """하루 한도의 날짜: 한국 시각(서버는 UTC 라 한국 오전 9시에 초기화됐다)"""
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 3600))


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


GUEST = re.compile(r"[0-9a-f]{16}")
GUEST_LIMITS = {"upload": 5, "agent": 8, "illustrate": 20, "retry": 5, "translate": 5}  # 심사용 키를 쓰는 브라우저(게스트) 한 곳의 하루 한도: 한 사람이 심사위원 전체 몫을 다 쓰지 않게


def guest_id(request):
    g = getattr(request.state, "gid", "") or request.cookies.get("sc_guest", "")
    return g if GUEST.fullmatch(g or "") else ""


def ident(request, role=None):
    """카드 묶음의 주인 이름. 심사용 키는 하나라 브라우저마다 붙인 게스트 번호로 나눈다(11-04: 심사위원끼리 '내가 만든 카드'가 섞였다)"""
    role = who(request) if role is None else role
    return f"judge:{guest_id(request)}" if role == "judge" and guest_id(request) else role


def owns(request, role, run_id):
    """이 사람이 카드 묶음의 주인인가. 게스트 번호 전에 심사용 키로 만든 묶음(주인 'judge')은 심사용 키 모두가 쓴다"""
    o = owner_of(run_id)
    return bool(role) and (o == ident(request, role) or (role == "judge" and o == "judge"))


def client_ip(request):
    # x-forwarded-for 는 클라이언트가 넣는 값이라 앞 토큰은 위조된다(가짜 IP 로 로그인 무차별·/now 폭주 한도를 피했다, 11-04 보안 검수).
    # Railway 는 프록시 1단: 실제 IP 는 맨 뒤 항목. 프록시가 없는 로컬은 헤더가 없어 request.client.host 로 떨어진다.
    xff = request.headers.get("x-forwarded-for", "")
    return (xff.split(",")[-1].strip() if xff else (request.client.host if request.client else "")) or "?"


RATE = {}


def too_fast(key, n, window, count=True):
    """간단한 횟수 제한(메모리): window 초 안에 n 번 넘으면 True. count=False 면 세지 않고 보기만"""
    now = time.time()
    q = [t for t in RATE.get(key, []) if now - t < window]
    if len(RATE) > 20000:
        RATE.clear()
    RATE[key] = q + [now] if count else q
    return len(q) >= n


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
    if path != "/api/upload" and int(request.headers.get("content-length") or 0) > 12_000_000:  # 사진 6장 넘는 본문은 받지 않는다(메모리)
        return JSONResponse({"error": "request too large"}, 413)
    if NOW_PATH.match(path) and request.method == "POST":  # 키 없는 안경·학습자 요청: 아이피마다 횟수 제한(가짜 '도와줘요'·상태 파일 쓰기 폭주 막기)
        kind = path.rsplit("/", 1)[1]
        if too_fast(("now", kind, client_ip(request)), {"now": 240, "call": 20, "mark": 60}[kind], 60):
            return JSONResponse({"error": "too many requests"}, 429)
    if not APP_KEY or request.method in ("GET", "HEAD") or NOW_PATH.match(path):
        return await call_next(request)
    if path.endswith(PAID_PATHS) and spend.over():  # 누적 비용 상한: Meta 를 부르는 요청은 모두 거절(보기·손으로 넘기기는 그대로)
        return JSONResponse({"error": "credit cap reached", "cap": spend.CAP}, 402)
    if path == "/login" and request.method == "POST":
        if too_fast(("login", client_ip(request)), 10, 600, count=False):  # 키 맞히기 막기: 아이피마다 10분에 틀린 키 10번(맞은 로그인은 세지 않는다)
            return JSONResponse({"error": "too many attempts, try again later"}, 429)
        k = str((await request.form()).get("k", ""))
        for name, key in [("sc_key", APP_KEY), ("sc_judge", JUDGE_KEY)] + [("sc_teacher", tk) for tk in TEACHERS.values()]:
            if eq(k, key):
                r = JSONResponse({"ok": True})
                r.set_cookie(name, key, max_age=60 * 60 * 24 * 30, httponly=True, secure=True, samesite="lax")
                return r
        too_fast(("login", client_ip(request)), 10, 600)
        return JSONResponse({"error": "wrong key"}, 401)
    role = who(request)
    m = RUN_PATH.match(path)
    kind = next((k for k in PUBLIC_LIMITS if path.endswith("/" + k)), None) if m else None
    if not role and kind:  # 학습자 기기(키 없음): 따라 하기 판단·확인하기·기록만, 카드 묶음마다 하루 한도(크레딧 보호)
        today = kst_day()
        if PUBLIC_USE["day"] != today:
            PUBLIC_USE.update(day=today, n={})
        if not (RUNS / m.group(1)).is_dir():  # 없는 카드 묶음 id 로는 세지도 않는다(상태 파일이 끝없이 커지지 않게)
            return JSONResponse({"error": "no such card set"}, 404)
        used, total = PUBLIC_USE["n"].setdefault(m.group(1), {}), PUBLIC_USE["n"].setdefault("*", {})
        if used.get(kind, 0) >= PUBLIC_LIMITS[kind] or total.get(kind, 0) >= PUBLIC_TOTAL.get(kind, 10**9):
            return JSONResponse({"error": "daily limit for this card set"}, 429)
        used[kind] = used.get(kind, 0) + 1; total[kind] = total.get(kind, 0) + 1  # 처리 전에 자리를 잡는다: 동시에 몰린 요청이 모두 검사를 통과하던 것을 막는다
        request.state.who = "learner"
        r = await call_next(request)
        if 400 <= r.status_code < 500:  # 빈·잘못된 요청은 돌려준다(돈 안 들이고 그날 따라 하기를 막지 못하게). 5xx 는 Meta 를 이미 불렀을 수 있어 센다
            used[kind] -= 1; total[kind] -= 1
        save_state()
        return r
    if not role:
        return JSONResponse({"error": "key required"}, 401)
    use_only = path.endswith(("/coach", "/verify", "/records", "/log", "/copy"))  # 복사는 견본·남의 묶음에서도(새 묶음은 내 것)  # 따라 하기·확인하기·기록은 누구 카드 묶음이든(고치기가 아님)
    if m and not use_only and role != "admin" and (RUNS / m.group(1)).is_dir():  # 교사·심사 키는 자기가 올린 묶음만 고치고 지운다
        if m.group(1) in SEED_INDEX:
            return JSONResponse({"error": "sample card sets can't be changed"}, 403)
        if not owns(request, role, m.group(1)):
            return JSONResponse({"error": "someone else's card set"}, 403)
    if role == "judge":
        kind = next((k for k in JUDGE_LIMITS if path.rstrip("/").endswith(k)), None)
        if kind:  # 크레딧이 드는 요청만 센다. 날이 바뀌면 처음부터
            today = kst_day()
            if JUDGE_USE["day"] != today:
                JUDGE_USE.update(day=today, n={}, g={})
            if JUDGE_USE["n"].get(kind, 0) >= JUDGE_LIMITS[kind]:
                return JSONResponse({"error": "daily limit for the judge key"}, 429)
            gu = JUDGE_USE.setdefault("g", {}).setdefault(guest_id(request) or "-", {})
            if kind in GUEST_LIMITS and gu.get(kind, 0) >= GUEST_LIMITS[kind]:
                return JSONResponse({"error": "daily limit for this browser"}, 429)
            JUDGE_USE["n"][kind] = JUDGE_USE["n"].get(kind, 0) + 1  # 처리 전에 센다(동시 요청 경쟁), 4xx 면 아래에서 돌려준다
            gu[kind] = gu.get(kind, 0) + 1
    request.state.who = ident(request, role)  # 주인 이름(심사용 키는 judge:게스트번호): 올리기·사본·저장 한도가 이 이름으로
    if m and not use_only and (RUNS / m.group(1)).is_dir():  # 누가 무엇을 바꿨는지(따라 하기 판단은 너무 잦아서 뺀다)
        with (RUNS / m.group(1) / "audit.jsonl").open("a") as f:
            f.write(json.dumps({"t": round(time.time()), "who": role, "do": f"{request.method} {path[len(m.group(0)):] or '/'}"}, ensure_ascii=False) + "\n")
    r = await call_next(request)
    if role == "judge" and kind:  # 4xx 는 돈이 안 든 요청이라 돌려준다. 5xx 는 Meta 를 부른 뒤 실패했을 수 있어 그대로 센다
        if 400 <= r.status_code < 500:
            JUDGE_USE["n"][kind] -= 1
            g = JUDGE_USE.get("g", {}).get(guest_id(request) or "-", {})
            if kind in g:
                g[kind] -= 1
        save_state()
    return r


@app.middleware("http")
async def guest_cookie(request: Request, call_next):
    """브라우저마다 게스트 번호(무작위, 이름·기기 정보 없음). 심사용 키로 만든 카드를 브라우저별로 나누는 데만 쓴다"""
    g = request.cookies.get("sc_guest", "")
    fresh = not GUEST.fullmatch(g)
    request.state.gid = secrets.token_hex(8) if fresh else g
    r = await call_next(request)
    if fresh:
        r.set_cookie("sc_guest", request.state.gid, max_age=60 * 60 * 24 * 90, httponly=True, secure=True, samesite="lax")
    return r


CARDS_LOCK = threading.Lock()  # cards.json 읽고-고치고-쓰기가 동시에 겹치지 않게
RUNNING, RUNNING_LOCK = set(), threading.Lock()  # 파이프라인이 도는 실행 id: 같은 영상을 또 올려도 두 번 돌리지 않게
CARD_PATH = re.compile(r"cards/[\w.-]+\.(jpg|png)")
RUN_FILE = re.compile(r"[\w.-]+\.(jpg|png)")


@app.get("/runs/{run_id}/{sub}/{name}")
def run_file(run_id: str, sub: str, name: str):
    """키 없이 내주는 것은 카드 그림(cards/)과 장면 고르기 사진(frames/)뿐. 예전에는 실행 폴더 전체를 열어
    따라 하기 기록·받아쓴 글·진행 기록·소유 교사 이름까지 주소만 알면 받을 수 있었다(11-02 검토)"""
    if sub not in ("cards", "frames") or not RUN_FILE.fullmatch(name):
        raise HTTPException(404)
    f = run_dir(run_id) / sub / name
    if not f.is_file():
        raise HTTPException(404)
    return FileResponse(f)


def run_dir(run_id):
    d = RUNS / run_id
    if not run_id.isalnum() or not d.is_dir():
        raise HTTPException(404, "없는 실행입니다")
    return d


def read(d, name, default=None):
    p = d / name
    try:  # 반쯤 쓰인 파일 하나가 목록 전체를 500 으로 만들지 않게(없는 것처럼 다룬다)
        return json.loads(p.read_text()) if p.exists() else default
    except ValueError:
        return default


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


def save_cards(d, data):
    """cards.json 은 공개 GET·진행 폴링이 수시로 읽는다: 반쯤 쓴 파일을 읽지 않게 바꿔 끼워 쓴다"""
    atomic(d / "cards.json", lambda tmp: tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1)))


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


@app.get("/static/{name}")
def static_js(name: str):
    """3D 접기 카드 스크립트만 내보낸다(리포의 다른 파일은 열지 않는다)"""
    if name in ("hero_en.mp4", "hero_ko.mp4", "hero_en.jpg", "hero_ko.jpg"):  # 처음 화면의 앱 화면 녹화
        return FileResponse(ROOT / "static" / name, media_type="video/mp4" if name.endswith(".mp4") else "image/jpeg")
    if name not in ("fold.js", "fold3d.js"):
        raise HTTPException(404)
    return FileResponse(ROOT / "static" / name, media_type="text/javascript")


@app.get("/api/runs")
def runs(request: Request):
    """처음 화면 목록. 키가 없으면 견본만: 교사가 올린 카드 묶음은 주소(추측하기 어려운 id)를 아는 사람만 연다"""
    out, role = [], who(request)
    for d in sorted(RUNS.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        prog = read(d, "progress.json") if d.is_dir() else None
        if prog and (role == "admin" or d.name in SEED_INDEX or owns(request, role, d.name)):
            data = read(d, "cards.json")
            cs = data["cards"] if data else []
            seed = SEED_INDEX.get(d.name, {})
            out.append({"id": d.name, "video": prog["video"], "title": (data or {}).get("title") or seed.get("title", ""), "title_en": seed.get("title_en", ""), "use": seed.get("use", ""),
                        "job": seed.get("job_en" if request.query_params.get("ui") == "en" else "job", ""), "custom": seed.get("custom", False),
                        "done": data is not None, "count": len(cs),
                        "failed": data is None and (prog.get("events") or [{}])[-1].get("stage") == "error",
                        "issues": len(data["problems"]) if data else 0, "thumb": seed.get("thumb") or (cs[0]["image"] if cs else None),  # 견본은 자막 없는 장면을 썸네일로
                        "stage": storage.stage(d), "delete_on": None if d.name in SEED_INDEX else storage.delete_on(d),
                        # 목록 정리(폴더·거르기·정렬): 폴더, 만든 사람 확인 여부, 마지막으로 고친 때·쓴 때
                        "cats": seed.get("cats", []), "mode": (data or {}).get("mode", "together"), "no_done": bool((data or {}).get("no_done")), "fold3d": bool((data or {}).get("fold")),
                        "folder": (data or {}).get("folder", ""), "edited": (data or {}).get("edited_at") or d.stat().st_mtime, "used": storage.last_used(d),
                        "reviewed": d.name in SEED_INDEX or bool(data and data.get("reviewed_at") and data.get("reviewed_at") == data.get("edited_at"))})
    return out


@app.post("/api/runs/{run_id}/copy")
def copy_run(run_id: str, request: Request):
    """견본(또는 내 카드 묶음)을 내 카드 묶음으로 복사해 고쳐 쓴다. 새 id, 주인은 복사한 사람, 만든 사람 확인은 다시 처음부터"""
    src = run_dir(run_id)
    data = read(src, "cards.json")
    if data is None:
        raise HTTPException(404, "아직 카드가 없습니다")
    role = getattr(request.state, "who", "admin")
    if role != "admin":  # 저장 한도(올리기와 같은 기준)
        n, used = storage.owned_usage(RUNS, UPLOADS, role)
        if n >= storage.TEACHER_MAX_SETS or used + storage.size(src) > storage.TEACHER_QUOTA_MB << 20:
            raise HTTPException(403, f"저장 한도({storage.TEACHER_MAX_SETS}묶음·{storage.TEACHER_QUOTA_MB}MB)를 넘었습니다")
    new = uuid.uuid4().hex[:12]
    dst = RUNS / new
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("owner.txt", "audit.jsonl", "coach_log.jsonl", "records.jsonl", "marks.jsonl", "used", "*.tmp"))
    (dst / "owner.txt").write_text(role)
    prog = read(dst, "progress.json") or {}
    if prog.get("video_path"):  # 영상 경로는 복사본의 영상으로
        prog["video_path"] = str(dst / "video.mp4") if (dst / "video.mp4").exists() else prog["video_path"]
        text = json.dumps(prog, ensure_ascii=False, indent=1)
        atomic(dst / "progress.json", lambda t: t.write_text(text))
    seed = SEED_INDEX.get(run_id, {})
    title = (data.get("title") or seed.get("title") or "").replace(" (견본)", "").strip()
    for k in ("seed_v", "reviewed_at", "folder"):
        data.pop(k, None)
    data["title"] = (title + (" 사본" if title else "사본"))[:60]
    data["edited_at"] = time.time()
    save_cards(dst, data)
    return {"id": new}


@app.post("/api/runs/{run_id}/folder")
def set_folder(run_id: str, body: dict):
    """카드 묶음을 폴더로 옮긴다(빈 문자열 = 폴더 없음). 카드 내용은 그대로라 고친 시각·만든 사람 확인은 바뀌지 않는다"""
    d = run_dir(run_id)
    name = re.sub(r"\s+", " ", str(body.get("folder") or "")).strip()[:30]
    with CARDS_LOCK:
        data = read(d, "cards.json")
        if data is None:
            raise HTTPException(404, "아직 카드가 없습니다")
        data["folder"] = name
        save_cards(d, data)
    return {"folder": name}


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    """카드 묶음 지우기: 실행 폴더와, 올린 영상이 업로드 폴더에 있으면 그것도"""
    d = run_dir(run_id)
    with RUNNING_LOCK:
        if run_id in RUNNING:
            raise HTTPException(409, "아직 만드는 중입니다")
    video = Path((read(d, "progress.json") or {}).get("video_path") or "")
    keep = storage.shared(video, RUNS, d)  # 복사본이나 같은 파일을 올린 다른 묶음이 쓰는 영상은 남긴다
    shutil.rmtree(d)
    if video.is_file() and video.resolve().parent == UPLOADS.resolve() and not keep:
        video.unlink()
    for k in [k for k in NOW if k == run_id or k.startswith(run_id + "|")]:  # 짝 코드가 붙은 키("id|코드")도
        NOW.pop(k, None)
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
def upload(request: Request, file: UploadFile, local: bool = Form(False)):  # async 가 아니다: 읽기·해시·ffprobe 동안 다른 요청(/now 등)이 멈췄다(11-02 검토)
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
        if Path(file.filename or "").suffix.lower() == ".webm" or (file.content_type or "").startswith("video/webm"):  # 브라우저로 바로 찍은 영상(webm): 길이 정보가 없고 뒤 단계(ffmpeg 자르기)가 mp4를 가정한다 → mp4로 바꾼다
            conv = tmp.with_suffix(".mp4")
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(conv)], capture_output=True)
            if r.returncode or not conv.exists():
                conv.unlink(missing_ok=True)
                raise HTTPException(400, "영상을 읽지 못했습니다")
            os.replace(conv, tmp)
            file.filename = Path(file.filename or "camera.webm").stem + ".mp4"
        secs = video_seconds(tmp)
        if not 0 < secs <= MAX_VIDEO_SEC:
            raise HTTPException(400, f"영상 길이는 {MAX_VIDEO_SEC // 60}분 이하여야 합니다" if secs else "영상을 읽지 못했습니다")
        dest = UPLOADS / f"{h.hexdigest()[:12]}_{Path(file.filename).name}"
        fresh = not dest.exists()
        if fresh:
            os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    role = getattr(request.state, "who", "admin")
    if role != "admin":  # 교사(심사) 한 사람이 저장소를 다 쓰지 않게
        n, used = storage.owned_usage(RUNS, UPLOADS, role)
        if n >= storage.TEACHER_MAX_SETS or used + dest.stat().st_size > storage.TEACHER_QUOTA_MB << 20:
            if fresh:
                dest.unlink(missing_ok=True)  # 한도를 넘어 거절한 영상은 남기지 않는다
            raise HTTPException(403, f"저장 한도({storage.TEACHER_MAX_SETS}묶음·{storage.TEACHER_QUOTA_MB}MB)를 넘었습니다")
    rid = h.hexdigest()[:12]
    if role != "admin" and (owner_of(rid) not in ("", role) or rid in SEED_INDEX):  # 다른 교사(또는 견본)와 같은 영상: 그 묶음으로 보내면 고칠 수 없었다 → 올린 사람마다 따로
        rid = hashlib.sha256(f"{rid}|{role}".encode()).hexdigest()[:12]
    run = pipeline.Run(dest, rid)
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
            pipeline.main(video, local=local, run_id=run_id)
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
    return agent.run(data["cards"], data.get("duration", len(list((d / "frames").glob("*.jpg")))), instruction,
                     "en" if body.get("lang") == "en" else "ko")  # 메모는 교사 화면 언어로


@app.post("/api/runs/{run_id}/translate")
def translate_cards(run_id: str, body: dict):
    """카드 문장을 한 언어 더(보호자·동료의 언어). 돈이 든 결과라 바로 저장하되 '확인 전'으로: 만든 사람이 되옮긴 문장을 보고 확인해야 보인다"""
    import translate
    d = run_dir(run_id)
    language = str(body.get("lang", "")).strip()[:40]
    if not language or not read(d, "cards.json"):
        raise HTTPException(400, "옮길 언어가 없습니다")
    src = read(d, "cards.json")["cards"]
    asked = {c["n"]: c.get("ko", "") for c in src}  # 옮긴 그 문장(그사이 고친 문장을 '최신 번역'으로 착각하지 않게)
    t = translate.run(src, language)
    if not t["cards"]:
        raise HTTPException(502, "번역 결과가 비었습니다. 다시 해 보세요")
    with CARDS_LOCK:
        data = read(d, "cards.json")
        by = {c["n"]: c for c in t["cards"]}
        for c in data["cards"]:
            c.pop("x", None); c.pop("xb", None); c.pop("xsrc", None)
            if c["n"] in by:
                c.update(x=by[c["n"]]["x"], xb=by[c["n"]].get("xb"), xsrc=asked.get(c["n"], ""))
        data["extra"] = {"lang": language, "name": t["name"], "ok": False}
        save_cards(d, data)
    return {**data, "translate": {"problems": t["problems"], "cost": t["cost"]}}


@app.post("/api/runs/{run_id}/fold/step")
def fold_step(run_id: str, body: dict):
    """3D 접기: 카드 하나의 동작만 받는다(앞 카드까지의 프로그램과 지금 3D 모양 그림을 보고). 저장 안 함"""
    import fold_gen
    d = run_dir(run_id)
    storage.ensure_frames(d)  # 정리(compact)된 묶음은 1초 사진이 지워져 있다: 먼저 다시 뽑는다
    data = read(d, "cards.json")
    if not data or not isinstance(body.get("n"), int):
        raise HTTPException(400, "카드가 없습니다")
    lines = lambda k: [str(x)[:300] for x in body.get(k, [])][:10] if isinstance(body.get(k), list) else []
    prefix = body.get("prefix") if isinstance(body.get("prefix"), dict) else {}
    out = fold_gen.write_step(d, data["cards"], body["n"], prefix, body.get("current"), lines("problems"), lines("notes"))
    if out["ops"] is None:
        raise HTTPException(502, "접기 동작을 받지 못했습니다. 다시 해 보세요")
    return out


@app.post("/api/runs/{run_id}/fold/compare")
def fold_compare(run_id: str, body: dict):
    """3D 끝 모양과 시범 끝 장면을 Muse Spark 가 비교"""
    import fold_gen
    d = run_dir(run_id)
    storage.ensure_frames(d)  # 정리(compact)된 묶음은 1초 사진이 지워져 있다: 먼저 다시 뽑는다
    data = read(d, "cards.json")
    stills = body.get("stills") if isinstance(body.get("stills"), dict) else {}
    if not data or not stills:
        raise HTTPException(400, "비교할 그림이 없습니다")
    return fold_gen.compare(d, data["cards"], stills)


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
    p["title_en"] = SEED_INDEX.get(run_id, {}).get("title_en", "")
    p.pop("video_path", None)  # 서버 안 경로는 내보내지 않는다(11-04 보안 검수)
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
    heard = " ".join(x.get("text", "") for x in (read(d, "speech.json") or []) if isinstance(x, dict))  # 카드 문장의 숫자가 말소리에 있었는지 화면이 본다
    # 교사 확인: 마지막으로 고친 뒤 '다 됐어요'를 눌렀는가(견본은 확인된 것으로)
    reviewed = run_id in SEED_INDEX or bool(data.get("reviewed_at") and data.get("reviewed_at") == data.get("edited_at"))
    return {**data, "caught": caught, "tries": len(splits), "title_en": SEED_INDEX.get(run_id, {}).get("title_en", ""),
            "heard_nums": sorted(set(re.findall(r"\d+(?:[.,]\d+)?", heard))), "reviewed": reviewed, "sample": run_id in SEED_INDEX,
            "stage": storage.stage(d), "delete_on": storage.delete_on(d) if run_id not in SEED_INDEX else None}


@app.put("/api/runs/{run_id}/cards")
def save(run_id: str, body: dict):
    d = run_dir(run_id)
    with CARDS_LOCK:
        return _save(d, body)


NUM_KEYS = ("start", "end", "rep", "frame_t", "done_t", "v")
TEXT_KEYS = {"ko": 300, "en": 300, "en_src": 300, "object": 120, "look": 200, "check": 300, "x": 300, "xsrc": 300, "box_prompt": 120}


def clean_cards(cards):
    """클라이언트가 보낸 카드 배열을 그대로 믿지 않는다: n 은 서로 다른 양의 정수, 시간 값은 숫자, 글은 길이 제한(11-01 검수: 저장된 XSS·묶음 먹통)"""
    if not isinstance(cards, list) or not cards or len(cards) > 300:
        raise HTTPException(400, "카드 목록이 잘못됐습니다")
    seen = set()
    for c in cards:
        if not isinstance(c, dict) or not isinstance(c.get("n"), int) or isinstance(c.get("n"), bool) or c["n"] < 1 or c["n"] in seen:
            raise HTTPException(400, "카드 번호가 잘못됐습니다")
        seen.add(c["n"])
        for k in NUM_KEYS:
            if c.get(k) is not None and (isinstance(c[k], bool) or not isinstance(c[k], (int, float))):
                raise HTTPException(400, f"숫자여야 합니다: {k}")
        for k, lim in TEXT_KEYS.items():
            if c.get(k) is not None:
                if not isinstance(c[k], str):
                    raise HTTPException(400, f"글이어야 합니다: {k}")
                c[k] = c[k][:lim]
        if c.get("view") not in (None, "photo", "ill", "clip", "fold"):
            raise HTTPException(400, "보기 값이 잘못됐습니다")
        if c.get("box") is not None and not (isinstance(c["box"], list) and len(c["box"]) == 4 and all(isinstance(x, (int, float)) for x in c["box"])):
            raise HTTPException(400, "상자 값이 잘못됐습니다")
    return cards


def _save(d, body):
    data = read(d, "cards.json")
    if not data:
        raise HTTPException(404, "카드가 아직 없습니다")
    was_reviewed = bool(data.get("reviewed_at")) and data.get("reviewed_at") == data.get("edited_at")
    body["cards"] = clean_cards(body.get("cards"))
    same_cards = body["cards"] == data.get("cards")
    for c in body["cards"]:  # 사진·그림 경로는 실행 폴더의 cards/ 안 파일만
        for k in ("image", "ill"):
            if c.get(k) is not None and not (isinstance(c[k], str) and CARD_PATH.fullmatch(c[k])):
                raise HTTPException(400, f"잘못된 파일 경로입니다: {k}")
    data["cards"] = body["cards"]
    data["next_n"] = max(data.get("next_n", 0), max(c["n"] for c in data["cards"]) + 1)  # 카드 번호는 늘기만: 뺀 카드의 목소리·기록·3D 가 새 카드에 붙지 않게
    if isinstance(body.get("title"), str):
        data["title"] = body["title"].strip()[:60]
    if body.get("mode") in ("together", "alone"):  # 같이 하기(곁에 사람: 도와줘요) / 혼자 하기(여기서 막혔어요)
        data["mode"] = body["mode"]
    if body.get("pov") in ("first", "facing"):  # 시범 시점: 하는 사람 눈높이(기본) / 마주 보고 찍음(수어·춤)
        data["pov"] = body["pov"]
    if isinstance(body.get("no_done"), bool):  # 사람을 돕거나 다칠 수 있는 일: 기계가 '됐어요'라고 판단하지 않는다
        data["no_done"] = body["no_done"]
    if "fold" in body:  # 3D 접기 프로그램(브라우저가 검사한 것). 끄기는 None
        f = body["fold"]
        data["fold"] = f if isinstance(f, dict) and isinstance(f.get("steps"), list) and len(json.dumps(f)) < 50_000 else None
    if "extra" in body:  # 한 언어 더: 끄기(None) 또는 확인 표시만 받는다. 번역 글은 카드의 x
        e = body["extra"]
        data["extra"] = {"lang": str(e.get("lang", ""))[:40], "name": str(e.get("name", ""))[:40], "ok": e.get("ok") is True} if isinstance(e, dict) else None
    if data.get("extra") and any(c.get("xsrc", c.get("ko")) != c.get("ko") or not c.get("x") for c in data["cards"]):
        data["extra"]["ok"] = False  # 카드 문장이 바뀌거나 번역 없는 카드가 생기면 다시 확인
    data["problems"], data["warnings"] = check(data["cards"], data.get("duration", len(list((d / "frames").glob("*.jpg")))))
    data["status"] = "ok" if not data["problems"] else "needs_review"
    data["edited_at"] = time.time()
    if body.get("reviewed") is True or (was_reviewed and same_cards):  # 교사가 '다 됐어요'를 누름(그 뒤 카드를 고치면 다시 확인 전). 설정만 바꾼 저장은 그대로
        data["reviewed_at"] = data["edited_at"]
    save_cards(d, data)
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
    dur = (read(d, "cards.json") or {}).get("duration")
    if t < 0 or (dur and t >= dur):
        raise HTTPException(400, "영상 길이 밖의 시각입니다")
    img, hl = inside(d, card["image"]), inside(d, re.sub(r"\.(jpg|png)$", r"_hl.\1", card["image"]))  # png 원본을 덮어쓰지 않게
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
        save_cards(d, data)
    return card


@app.post("/api/runs/{run_id}/cards/{n}/illustrate")
def illustrate(run_id: str, n: int):
    """n번 카드 사진을 그림 카드로(Muse Image). 교사가 사진·그림 중 고른다."""
    d = run_dir(run_id)
    data = read(d, "cards.json")
    card = next((c for c in data["cards"] if c["n"] == n), None)
    if card is None:
        raise HTTPException(404, "없는 카드입니다")
    rel = re.sub(r"\.(jpg|png)$", "_ill.jpg", card["image"])  # png 원본을 덮어쓰지 않게
    inside(d, rel).write_bytes(pipeline.illustrate(inside(d, card["image"]), card.get("object", "")))  # 오래 걸리는 부분은 잠그지 않음
    with CARDS_LOCK:
        data = read(d, "cards.json")
        card = next((c for c in data["cards"] if c["n"] == n), None)
        if card is None:
            raise HTTPException(404, "없는 카드입니다")
        card.update(ill=rel, view="ill")
        save_cards(d, data)
    return card


@app.post("/api/runs/{run_id}/coach")
def coach_check(run_id: str, body: dict, request: Request):
    """따라 하기: 카메라 사진 몇 장으로 카드를 넘길지 정한다. 사진은 저장하지 않는다."""
    data = read(run_dir(run_id), "cards.json")
    if not data:
        raise HTTPException(404, "카드가 없습니다")
    ver = body.get("ver")
    if ver is not None and data.get("edited_at") and ver != data["edited_at"]:  # 따라 하는 동안 교사가 카드를 고쳤다 → 화면이 새 카드를 받게(판단 끔으로 바꾼 것도)
        return {"decision": "reload", "seen": 0}
    if data.get("no_done"):  # 사람을 돕는 일: 기계가 '다 했다'를 정하지 않는다(카드는 사람이 넘긴다)
        raise HTTPException(409, "이 카드 묶음은 직접 넘겨요")
    learner = getattr(request.state, "who", "") == "learner"  # 키 없는 기기: 사진 4장·장당 40만 자까지(화면은 480px 사진 4장을 보낸다). 6장·큰 사진으로 비용을 부풀리지 못하게(11-04 보안 검수)
    frames = [f for f in body.get("frames", [])[-(4 if learner else 6):] if isinstance(f, str) and f.startswith("data:image/jpeg;base64,") and len(f) < (400_000 if learner else 1_500_000)]  # 사진당 크기 제한(비용)
    try:
        cur = int(body.get("cur", 1))
    except (TypeError, ValueError):
        raise HTTPException(400, "카드 번호가 틀렸습니다")
    if len(frames) < 2 or not 1 <= cur <= len(data["cards"]):
        raise HTTPException(400, "사진이 부족하거나 카드 번호가 틀렸습니다")
    ref, d, local = None, run_dir(run_id), bool(body.get("local")) and not APP_KEY  # 이 맥 Glimmer 는 키를 설정하지 않은 로컬에서만: 배포 서버에서 local 을 보내면 없는 서버를 불러 500 → 한도만 깎이고 알림이 쏟아졌다(11-04 보안 검수)
    if body.get("live"):  # 실시간 확인: 지금 카드의 완료 기준 사진을 같은 판단에 넣는다
        ref = pipeline.data_url(verify.reference(d, data["cards"][cur - 1], "after"))
    # Meta API 판단은 시범의 단계 끝 사진들과 맞춘다(이 맥 Glimmer 는 사진이 많으면 느려 예전 방식 그대로)
    try:
        prev_match = int(body.get("prev_match", -1))
    except (TypeError, ValueError):
        prev_match = -1
    try:
        on_card = float(body["on_card"]) if body.get("on_card") is not None else None  # 이 카드가 뜬 지 몇 초
    except (TypeError, ValueError):
        on_card = None
    wide = bool(body.get("ahead")) or coach.stuck(data["cards"], cur, on_card)  # 막혔거나 앞서 갔으면 남은 단계 끝 사진을 전부(11-03)
    refs = None if local else coach.state_refs(d, data["cards"], cur, wide)
    try:
        prev_seen = int(body.get("prev_seen") or 0)
    except (TypeError, ValueError):
        prev_seen = 0
    return coach.check(data["cards"], cur, frames, prev_seen, local, ref, refs,
                       prev_match, bool(refs) and coach.change(d, data["cards"], cur) < coach.SIMILAR, on_card, data.get("pov") == "facing")


# 안경 화면(Ray-Ban Display 웹앱)과 따라 하기 화면이 같은 카드를 보게 하는 공유 상태. 메모리에만 둔다


@app.get("/glasses")
def glasses():
    return FileResponse(ROOT / "static" / "glasses.html")


@app.get("/api/runs/{run_id}/now")
def now_get(run_id: str, s: str = ""):
    st = NOW.get(now_key(run_id, s))
    if st is None:
        return {"i": 0, "again": False, "by": "", "v": 0, "lv": 0}
    st["seen"] = round(time.time())  # 따라 하기·안경 화면이 아직 열려 있다(현황판이 닫힌 화면의 부름을 계속 보여 주지 않게)
    return st


def now_key(run_id, s):
    """같은 카드 묶음을 여러 학생이 동시에 쓰면 따라 하기 화면마다 짝 코드(s)로 나눈다. 없으면 카드 묶음 하나에 하나"""
    s = re.sub(r"[^a-z0-9]", "", str(s).lower())[:8]
    return f"{run_id}|{s}" if s else run_id


VRES_KEYS = ("id", "result", "ko", "en")  # 안경에 돌려주는 확인 결과(glassesResult 가 보내는 키만)


@app.post("/api/runs/{run_id}/now")
def now_set(run_id: str, body: dict):
    n = len(read(run_dir(run_id), "cards.json")["cards"])
    key = now_key(run_id, body.get("s", ""))
    prev = NOW.get(key, {})
    v = prev.get("v", 0) + 1
    try:
        i = max(0, min(n - 1, int(body.get("i", 0)))); int(body.get("lv") or 0); int(body.get("vreq") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "숫자가 아닙니다")
    if key not in NOW and sum(1 for k in NOW if k.startswith(run_id)) >= 40:  # 묶음당 화면 수 상한(짝 코드를 바꿔 가며 늘리지 못하게): 오래된 것부터 지운다
        old = min((k for k in NOW if k.startswith(run_id)), key=lambda k: NOW[k].get("t", 0))
        NOW.pop(old, None)
    # 병합 규칙(11-01 검수): 휴대폰이 안경의 마지막 변경을 아직 못 본 채(base < v) 보낸 카드·도움 값은 적용하지 않는다(안경 넘김이 되돌아가지 않게).
    # 휴대폰은 다음 폴링에서 안경 변경을 받아 적용한다. 응답의 held 는 '적용 안 함'
    try:
        base = int(body["base"]) if "base" in body else None
    except (TypeError, ValueError):
        raise HTTPException(400, "숫자가 아닙니다")
    if body.get("by") == "coach" and prev.get("by") == "glasses" and base is not None and base < prev.get("v", 0):
        if isinstance(body.get("vres"), dict):  # 확인 결과는 그래도 전한다
            prev["vres"] = {k: str(x)[:80] for k, x in list(body["vres"].items())[:8] if k in VRES_KEYS}
        prev["t"] = round(time.time())
        return {**prev, "held": True}
    keep = prev.get("i") == i and not body.get("fin")  # '도와줘요'는 그 카드에 있는 동안만 켜 둔다(다음 카드로 가면 저절로 꺼짐)
    NOW[key] = {"call": prev.get("call", 0) if keep else 0, "why": prev.get("why", "") if keep else "","i": max(0, min(n - 1, int(body.get("i", 0)))), "again": bool(body.get("again")), "by": str(body.get("by", ""))[:10], "v": v,
                   "lv": max(0, min(4, int(body.get("lv") or 0))), "fin": bool(body.get("fin")), "t": round(time.time()), "seen": round(time.time()),
                 # 안경 '확인' → 따라 하기 화면이 휴대폰 카메라로 찍어 확인(vreq), 결과를 안경에 돌려준다(vres)
                 # 확인 요청·결과는 보낸 쪽이 바꿀 때만 바뀐다(휴대폰의 평소 동기화가 안경의 확인 요청을 지우지 않게)
                 "vreq": int(body.get("vreq") or 0) if "vreq" in body else prev.get("vreq", 0),
                 "vres": ({k: str(x)[:80] for k, x in list(body["vres"].items())[:8] if k in VRES_KEYS} if isinstance(body.get("vres"), dict) else None) if "vres" in body else prev.get("vres")}  # fin = 마지막 단계까지 마침  # 도움 단계(0=끔, 1 글 → 4 움직임)
    save_state()
    return NOW[key]


@app.post("/api/runs/{run_id}/mark")
def mark_stuck(run_id: str, body: dict):
    """혼자 하기: 따라 하는 사람(키 없음, 릴스 시청자 등)이 '여기서 막혔어요'. 카드 번호만 남는다(이름·사진·기기 정보 없음).
    만든 사람의 고치기 화면 '자주 막힌 카드'에 모인다"""
    d = run_dir(run_id)
    data = read(d, "cards.json")
    n = body.get("n")
    if not data or not any(c.get("n") == n for c in data["cards"]):
        raise HTTPException(400, "없는 카드입니다")
    now = time.time()
    MARKS[run_id] = [t for t in MARKS.get(run_id, []) if now - t < 60][-59:] + [now]
    if len(MARKS[run_id]) > 30:
        raise HTTPException(429, "잠시 뒤에 다시 눌러 주세요")
    f = d / "marks.jsonl"
    if f.exists() and f.stat().st_size > 500_000:  # 오래된 것부터 버린다
        f.write_text("\n".join(f.read_text().splitlines()[-2000:]) + "\n")
    with f.open("a") as fh:
        fh.write(json.dumps({"t": round(now), "kind": "mark", "n": n}) + "\n")
    return {"ok": True}


@app.post("/api/runs/{run_id}/call")
def call_set(run_id: str, body: dict):
    """만든 사람 부르기: 따라 하는 사람(안경·휴대폰)이 누르거나, 도움이 끝까지 가도 안 될 때 화면이 저절로. 만든 사람이 '갔어요'로 끈다.
    카드 번호·도움 단계만 오가고 사진·이름은 없다"""
    key = now_key(run_id, body.get("s", ""))
    if key not in NOW:
        raise HTTPException(404, "따라 하는 화면이 없습니다")
    on = bool(body.get("call"))
    if body.get("ack"):  # 만든 사람이 현황판에서 '갈게요': 부름은 끄고, 따라 하는 화면·안경에 '오고 있어요'
        NOW[key] = {**NOW[key], "call": 0, "why": "", "ack": round(time.time()), "v": NOW[key].get("v", 0) + 1}
        save_state()
        return NOW[key]
    NOW[key] = {**NOW[key], "call": round(time.time()) if on else 0, "why": str(body.get("why", ""))[:10] if on else "", "v": NOW[key].get("v", 0) + 1, "t": round(time.time())}
    save_state()
    return NOW[key]


@app.get("/api/runs/{run_id}/live")
def live(run_id: str, request: Request):
    """만든 사람의 현황판: 이 카드 묶음을 지금(2분 안) 따라 하는 화면들. 키가 있는 사람만, 교사 키는 자기 묶음·견본만(/api/calls 와 같은 소유 규칙)"""
    role = who(request)
    if not role:
        raise HTTPException(401, "key required")
    if role.startswith("teacher") and run_id not in SEED_INDEX and owner_of(run_id) != role:
        raise HTTPException(403, "someone else's card set")
    now, out = time.time(), []
    for k, st in NOW.items():
        if k.split("|")[0] == run_id and alive(st, now) and not st.get("fin"):
            out.append({"s": k.split("|")[1] if "|" in k else "", "by": st.get("by", ""), "i": st.get("i", 0), "lv": st.get("lv", 0), "call": st.get("call", 0), "why": st.get("why", ""), "t": st.get("t", 0)})
    return sorted(out, key=lambda x: (-bool(x["call"]), x["call"] or 0, -x["t"]))


def alive(st, now):
    """화면이 2분 안에 서버와 이야기했다(닫힌 브라우저의 부름·안 쓰는 화면을 현황판에서 뺀다)"""
    return now - max(st.get("seen", 0), st.get("t", 0)) < 120


@app.get("/api/calls")
def calls(request: Request):
    """만든 사람이 어느 화면에 있든 볼 부름: 내 카드 묶음과 견본에서 지금 '도와줘요'가 켜진 화면"""
    role = who(request)
    if not role:
        raise HTTPException(401, "key required")
    now, out = time.time(), []
    for k, st in list(NOW.items()):
        rid = k.split("|")[0]
        if not st.get("call") or st.get("fin") or not alive(st, now):
            continue
        if role.startswith("teacher") and rid not in SEED_INDEX and owner_of(rid) != role:
            continue
        data = read(RUNS / rid, "cards.json") or {}
        out.append({"run": rid, "title": data.get("title", ""), "s": k.split("|")[1] if "|" in k else "", "i": st.get("i", 0), "call": st["call"], "why": st.get("why", "")})
    return sorted(out, key=lambda x: x["call"])


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


GTTS_KEY = os.environ.get("GTTS_KEY") or (Path("~/.gtts_key").expanduser().read_text().strip() if Path("~/.gtts_key").expanduser().exists() else "")
SAY_VOICE = {"ko": ("ko-KR", "ko-KR-Chirp3-HD-Zephyr"), "en": ("en-US", "en-US-Chirp3-HD-Zephyr")}


@app.get("/api/runs/{run_id}/cards/{n}/say.mp3")
def card_say(run_id: str, n: int, l: str = "ko"):
    """카드 문장을 자연스러운 목소리(구글 Chirp3-HD)로. 문장이 바뀌면 새로 만들고, 같은 문장은 만든 파일을 다시 쓴다.
    키(GTTS_KEY)가 없거나 실패하면 404 → 화면이 기기 음성으로 읽는다. 카드에 있는 문장만 읽으니 만들 수 있는 양은 카드 수로 정해진다"""
    import base64, urllib.request
    d = run_dir(run_id)
    data = read(d, "cards.json")
    c = next((c for c in (data or {}).get("cards", []) if c.get("n") == n), None)
    text = str((c or {}).get(l) or "").strip()
    if not (GTTS_KEY and l in SAY_VOICE and text):
        raise HTTPException(404)
    out = d / "cards" / f"say_{n}_{l}_{hashlib.sha1(text.encode()).hexdigest()[:10]}.mp3"
    if not (out.exists() and out.stat().st_size):
        lang, name = SAY_VOICE[l]
        body = {"input": {"text": text}, "voice": {"languageCode": lang, "name": name}, "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.95}}
        try:
            req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize?key=" + GTTS_KEY,
                                         data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
            audio = base64.b64decode(json.loads(urllib.request.urlopen(req, timeout=20).read())["audioContent"])
        except Exception:
            raise HTTPException(404)
        tmp = out.with_name(f".{os.getpid()}_{threading.get_ident()}_{out.name}")
        tmp.write_bytes(audio)
        os.replace(tmp, out)
    return FileResponse(out, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/runs/{run_id}/demo.mp4")
def demo_video(run_id: str):
    """'작동 보기': 견본의 시범 영상(CC BY)을 따라 하기 카메라 대신 흘린다. 교사가 올린 영상은 내주지 않는다"""
    f = run_dir(run_id) / "video.mp4"
    if run_id not in SEED_INDEX or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="video/mp4")


@app.get("/api/runs/{run_id}/clip/{n}.mp4")
def card_clip(run_id: str, n: int, g: int = 0):
    g = 1 if g else 0
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
def qr(run_id: str, request: Request, to: str = "tablet", lang: str = "ko", s: str = "", m: str = "ko", log: str = ""):
    """학생 기기로 넘기는 QR: 태블릿 보기나 안경 화면 주소(보기는 키 없이 된다)"""
    import segno
    run_dir(run_id)
    base = f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"
    lang = lang if lang in ("ko", "en", "both", "x") else "ko"
    m = "en" if m == "en" else "ko"  # lang=x(한 언어 더)일 때 위 줄 언어
    url = f"{base}/glasses?run={run_id}&lang={lang}" + ("&m=en" if lang == "x" and m == "en" else "") + (f"&s={re.sub(r'[^a-z0-9]', '', s.lower())[:8]}" if s else "") if to == "glasses" else f"{base}/?ui={lang if lang in ('ko', 'en') else m}#run={run_id}&view=tablet"
    if to == "coach":  # 노트북 앞 카메라 대신 휴대폰 뒤 카메라로 따라 하기(시험 기록 켬은 그대로 넘긴다)
        url = f"{base}/?ui={lang if lang in ('ko', 'en') else m}" + ("&log=1" if log == "1" else "") + f"#run={run_id}&view=coach"
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#11183a")
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
            rows.append({"id": d.name, "title_en": SEED_INDEX.get(d.name, {}).get("title_en", ""), "title": data.get("title") or SEED_INDEX.get(d.name, {}).get("title") or storage.progress(d).get("video", ""),
                         "owner": owner_of(d.name) or ("seed" if d.name in SEED_INDEX else "admin"), "stage": storage.stage(d),
                         "last_used": storage.last_used(d), "delete_on": storage.delete_on(d), "size": storage.report(d, UPLOADS)})
    du = shutil.disk_usage(RUNS)
    owners = {}
    for r in rows:
        o = owners.setdefault(r["owner"], {"sets": 0, "bytes": 0}); o["sets"] += 1; o["bytes"] += r["size"]["total"]
    return {"runs": rows, "owners": owners, "free": du.free, "total": du.total, "spend": {"usd": round(spend.total(), 2), "cap": spend.CAP},
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
    data = read(d, "cards.json") or {}
    if data.get("no_done"):
        raise HTTPException(409, "이 카드 묶음은 '됐어요' 판단을 하지 않아요")
    c = {**card_by_n(d, n), "pov": data.get("pov")}  # 마주 보기 시범이면 자세를 비교한다
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


@app.get("/api/runs/{run_id}/cards/{n}/similar")
def card_similar(run_id: str, n: int):
    """시작과 완료 기준 장면이 비슷한지(고치기 화면이 '기준 문장을 써 주세요'를 띄우는 데 씀)"""
    d = run_dir(run_id)
    diff = verify.similarity(d, card_by_n(d, n))
    return {"diff": round(diff, 3), "similar": diff < verify.SIMILAR}


@app.post("/api/runs/{run_id}/setup")
def coach_setup(run_id: str, body: dict):
    """따라 하기 시작 전 자리 잡기: 카메라가 시범과 같은 곳을 비슷한 시점에서 보는가(사진은 저장하지 않는다)"""
    data = read(run_dir(run_id), "cards.json")
    if not data:
        raise HTTPException(404, "카드가 없습니다")
    f = body.get("frame")
    if not (isinstance(f, str) and f.startswith("data:image/jpeg;base64,") and len(f) < 1_500_000):
        raise HTTPException(400, "사진이 없습니다")
    try:
        cur = max(1, min(len(data["cards"]), int(body.get("cur", 1))))
    except (TypeError, ValueError):
        cur = 1
    return coach.setup_check(run_dir(run_id), data["cards"], cur, f, data.get("title_en") or data.get("title") or "")


@app.get("/api/runs/{run_id}/cards/{n}/before.jpg")
def card_before(run_id: str, n: int):
    """단계 시작 모습(자리 잡기 때 카메라 위에 흐리게 겹친다)"""
    d = run_dir(run_id)
    return FileResponse(inside(d, str(verify.reference(d, card_by_n(d, n), "before").relative_to(d))))


@app.get("/api/runs/{run_id}/cards/{n}/after.jpg")
def card_after(run_id: str, n: int, request: Request, t: int | None = None):
    """완료 기준 사진(시범 영상에서 그 단계가 끝난 순간). t 를 주면 그 시각(고치기 화면이 저장 전에 미리 보여 줌).
    임의 t 는 키 있는 요청만: 키 없이 t 를 훑어 ffmpeg·디스크를 긁지 못하게(11-04 보안 검수). 키 없으면 카드의 기본 완료시각으로."""
    d = run_dir(run_id)
    card = card_by_n(d, n)
    if t is not None and has_key(request):
        card = {**card, "done_t": max(0, min(t, int(read(d, "cards.json").get("duration") or t)))}
    return FileResponse(inside(d, str(verify.reference(d, card, "after").relative_to(d))))


def add_record(d, row):
    """교사가 '기록 남기기'를 켰을 때만: 이름 없이 날짜·카드·결과·도움 단계"""
    f = d / "records.jsonl"
    if f.exists() and f.stat().st_size > 1_000_000:  # 키 없이 쌓이는 기록: 오래된 것부터 버린다
        f.write_text("\n".join(f.read_text().splitlines()[-5000:]) + "\n")
    with f.open("a") as fh:
        fh.write(json.dumps({"t": round(time.time()), **row}, ensure_ascii=False) + "\n")


@app.post("/api/runs/{run_id}/records")
def post_records(run_id: str, body: dict):
    """따라 하기 끝 화면의 카드별 도움 단계(기록 켰을 때)"""
    d = run_dir(run_id)
    try:
        rows = [{"kind": "coach", "n": int(r.get("n", 0)), "lv": int(r.get("lv", 0)), "s": str(body.get("s", ""))[:8]} for r in (body.get("rows") or [])[:50]]
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(400, "기록 형식이 잘못됐습니다")
    for r in rows:
        add_record(d, r)
    return {"ok": True}


LOG_KEYS = ("cur", "to", "by", "decision", "target", "ms", "n", "result", "lv", "finished", "match", "done_step")  # match·done_step: 어느 시범 사진과 맞췄는지


@app.post("/api/runs/{run_id}/log")
def post_log(run_id: str, body: dict):
    """시험 기록(주소에 log=1 일 때만 화면이 보냄): 따라 하기 판단·카드 넘김·확인 결과·도움 단계. 사진·이름 없음. coach_report.py 가 읽는다"""
    f = run_dir(run_id) / "coach_log.jsonl"
    if f.exists() and f.stat().st_size > 2_000_000:
        raise HTTPException(413, "log full")
    row = {"t": round(time.time(), 2), "s": str(body.get("s", ""))[:8], "kind": str(body.get("kind", ""))[:12]}
    row.update({k: body[k] for k in LOG_KEYS if isinstance(body.get(k), (int, float, str, bool))})
    with f.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.get("/api/runs/{run_id}/log")
def get_log(run_id: str, request: Request):
    if not has_key(request):
        raise HTTPException(401, "key required")
    f = run_dir(run_id) / "coach_log.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


def stuck_cards(rows):
    """기록에서 따라 하는 사람들이 자주 막힌 카드: 소리·움직임 도움까지 간 비율이 절반 이상(2번 이상 따라 했을 때)이거나, 확인에서 '달라요·아직'이 2번 이상"""
    by = {}
    for r in rows:
        s = by.setdefault(r.get("n"), {"n": r.get("n"), "tries": 0, "high": 0, "checks": 0, "miss": 0, "marks": 0})
        if r.get("kind") == "coach":
            s["tries"] += 1
            s["high"] += int(r.get("lv", 0)) >= 3
        elif r.get("kind") == "verify":
            s["checks"] += 1
            s["miss"] += r.get("result") in ("different", "not_yet")
        elif r.get("kind") == "mark":
            s["marks"] += 1
    out = [s for s in by.values() if (s["tries"] >= 2 and s["high"] * 2 >= s["tries"]) or s["miss"] >= 2 or s["marks"] >= 2]
    return sorted(out, key=lambda s: (s["high"] + s["miss"] + s["marks"], s["tries"]), reverse=True)


@app.get("/api/runs/{run_id}/stuck")
def get_stuck(run_id: str, request: Request):
    """고치기 화면: 자주 막힌 카드(기록이 있는 사람만 — 기록은 키가 있어야 본다)"""
    if not has_key(request):
        raise HTTPException(401, "key required")
    rows = []
    for name in ("records.jsonl", "marks.jsonl"):  # 같이 하기 기록 + 혼자 하기 '여기서 막혔어요'
        f = run_dir(run_id) / name
        rows += [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []
    return stuck_cards(rows)


@app.get("/api/runs/{run_id}/records")
def get_records(run_id: str, request: Request):
    """학습 기록은 키가 있는 사람만(보기 공개와 달리)"""
    if not has_key(request):
        raise HTTPException(401, "key required")
    f = run_dir(run_id) / "records.jsonl"
    return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []


@app.get("/api/me")
def me(request: Request):
    """화면이 미리 알기 위한 역할(키 값은 주지 않는다): 큰 영상을 다 올린 뒤에야 키를 묻지 않게, 관리자 링크는 관리자에게만"""
    r = who(request)
    return {"role": r.split(":")[0] if r else None}


@app.get("/api/health")
def health():
    """상태 점검(Railway healthcheck·바깥 감시용): 저장 공간, 도는 작업, 키 여부"""
    du = shutil.disk_usage(RUNS)
    return {"ok": du.free > MIN_FREE_GB << 30 and du.used / du.total < 0.9, "free_gb": round(du.free / 2**30, 1), "used_pct": round(du.used / du.total * 100),
            "card_sets": sum(1 for d in RUNS.iterdir() if d.is_dir()), "making": len(RUNNING), "api_key": bool(pipeline.API_KEY), "spend_capped": spend.over(),
            "persistent": bool(os.environ.get("DATA_DIR"))}  # 배포에 DATA_DIR(볼륨)이 없으면 장부·카드가 재배포 때 사라진다


@app.get("/api/runs/{run_id}/export.zip")
def export(run_id: str, request: Request):
    """카드 묶음 내려받기(백업·다른 서버로 옮기기): 카드·사진·그림·제목. 영상과 1초 사진은 빼서 작게"""
    import zipfile
    d = run_dir(run_id)
    role = who(request)
    if APP_KEY and run_id not in SEED_INDEX and role != "admin" and not owns(request, role, run_id):  # 주인만(주소를 아는 학습자가 묶음째 받지 못하게, 11-04 보안 검수)
        raise HTTPException(403, "내 카드 묶음만 내려받을 수 있어요")
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
