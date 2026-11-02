# Meta API 누적 비용 장부와 상한. 서버가 Meta 를 부르는 세 곳(모델 응답·받아쓰기·그림)이 부르기 전에 guard(), 부른 뒤 add().
# 상한(SPEND_CAP_USD, 기본 $140 — 해커톤 크레딧 $150 안)에 닿으면 비용이 드는 요청을 모두 거절한다(보기·인쇄·손으로 넘기기는 그대로).
# 장부는 서버 저장 공간(DATA_DIR)의 spend.json(이 서버가 쓴 금액). 합계 = SPEND_ALREADY_USD(장부 밖에서 이미 쓴 금액, 콘솔에서 확인) + 장부.
# 기존 사용액은 변수라서 콘솔 금액을 보고 언제든 고칠 수 있다.
import json, os, threading, time
from pathlib import Path

FILE = Path(os.environ.get("DATA_DIR") or Path(__file__).parent) / "spend.json"
CAP = float(os.environ.get("SPEND_CAP_USD") or 140)
ALREADY = float(os.environ.get("SPEND_ALREADY_USD") or 0)
LOCK = threading.Lock()


class CapReached(RuntimeError):
    pass


def _read():
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {"usd": 0.0, "since": round(time.time())}


def total():
    return ALREADY + _read()["usd"]


def over():
    return total() >= CAP


def guard():
    if over():
        raise CapReached(f"credit cap ${CAP:.0f} reached")


def add(usd):
    if not usd:
        return
    with LOCK:
        d = _read()
        d["usd"] = round(d["usd"] + float(usd), 6)
        tmp = FILE.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")  # 프로세스가 둘이어도(측정기와 서버) 임시 파일이 겹치지 않게
        tmp.write_text(json.dumps(d))
        os.replace(tmp, FILE)
