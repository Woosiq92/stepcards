# 따라 하기 시험 기록(coach_log.jsonl)을 데모에 쓸 숫자로 정리한다.
# 기록은 따라 하기 화면 주소에 log=1 을 붙였을 때만 쌓인다(사진·이름 없음).
# 사용: .venv/bin/python coach_report.py <카드 묶음 id> [--s 짝코드] [--remote]
#   --remote: 배포판(Railway)에서 기록을 받는다. 키는 .env.railway 의 APP_KEY 를 읽고 화면에 찍지 않는다
#   짝 코드를 안 주면 가장 최근 시험(마지막 start 가 있는 짝 코드)을 본다
import json, os, statistics, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
RUNS = Path(os.environ.get("DATA_DIR") or ROOT) / "runs"  # app.py 와 같은 곳
REMOTE = "https://stepcards-production.up.railway.app"
UNDO_SEC = 10  # 자동으로 넘긴 뒤 이 안에 사람이 '이전'으로 되돌리면 잘못 넘긴 것으로 본다


def load(run_id, remote):
    if not remote:
        f = RUNS / run_id / "coach_log.jsonl"
        return [json.loads(x) for x in f.read_text().splitlines() if x.strip()] if f.exists() else []
    key = next((ln.split("=", 1)[1].strip() for ln in (ROOT / ".env.railway").read_text().splitlines() if ln.startswith("APP_KEY=")), "")
    req = urllib.request.Request(f"{REMOTE}/api/runs/{run_id}/log", headers={"Cookie": f"sc_key={key}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def session(rows, s):
    """한 번의 시험 = 그 짝 코드의 마지막 start 부터 끝까지"""
    if not s:
        starts = [r for r in rows if r["kind"] == "start"]
        if not starts:
            sys.exit("기록에 start 가 없어요. 따라 하기 주소에 log=1 을 붙이고 카메라를 켰는지 확인해 주세요.")
        s = starts[-1]["s"]
    mine = [r for r in rows if r["s"] == s]
    last = max(i for i, r in enumerate(mine) if r["kind"] == "start")
    return s, mine[last:]


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__ or "사용: coach_report.py <카드 묶음 id> [--s 짝코드] [--remote]")
    run_id = args[0]
    s = args[args.index("--s") + 1] if "--s" in args else ""
    s, rows = session(load(run_id, "--remote" in args), s)
    start, n = rows[0], rows[0].get("n", 0)
    end = next((r for r in rows if r["kind"] == "end"), None)
    dur = (end or rows[-1])["t"] - start["t"]
    cards = [r for r in rows if r["kind"] == "card"]
    dec = [r for r in rows if r["kind"] == "decision"]
    ver = [r for r in rows if r["kind"] == "verify"]
    helps = [r for r in rows if r["kind"] == "help"]

    # 자동 넘김이 맞았는지: 넘긴 뒤 UNDO_SEC 안에 사람이 되돌렸으면 틀린 것(대리 지표, 화면 녹화로 한 번 더 대조)
    auto = [r for r in cards if r["by"] == "auto"]
    undone = [a for a in auto if any(c["by"] == "manual" and c["cur"] == a["to"] and c["to"] < a["to"] and 0 < c["t"] - a["t"] <= UNDO_SEC for c in cards)]
    # 사람이 직접 '다음'을 누른 곳 = 시스템이 넘기지 못한 곳
    manual_next = [r for r in cards if r["by"] in ("manual", "glasses") and r["to"] == r["cur"] + 1]
    by_check = [r for r in cards if r["by"] == "check"]
    entered_auto = {a["to"] for a in auto if a not in undone}

    ms = [r["ms"] for r in dec if isinstance(r.get("ms"), (int, float)) and r["decision"] != "none"]
    vms = [r["ms"] for r in ver if isinstance(r.get("ms"), (int, float)) and not str(r["result"]).startswith("error")]
    top = {}
    for h in helps:
        top[h["n"]] = max(top.get(h["n"], 1), h["lv"])
    lv_name = {1: "글", 2: "그림", 3: "소리", 4: "움직임"}

    print(f"카드 묶음 {run_id} · 짝 코드 {s} · {time.strftime('%m-%d %H:%M', time.localtime(start['t']))} 시작")
    print(f"걸린 시간 {dur / 60:.1f}분 · {'끝까지 다 함' if end and end.get('finished') else '중간에 멈춤'} · 카드 {n}장")
    print()
    print(f"자동으로 넘어간 카드 {len(auto)}번 · 그중 {UNDO_SEC}초 안에 되돌린 것 {len(undone)}번")
    print(f"자동으로 맞게 들어간 카드: {len(entered_auto)} / {max(n - 1, 0)} (첫 카드 제외)")
    print(f"사람이 직접 다음으로 넘긴 곳 {len(manual_next)}번 · 확인하기 뒤 넘긴 곳 {len(by_check)}번")
    if ms:
        print(f"따라 하기 판단 {len(ms)}번 · 걸린 시간 중앙값 {statistics.median(ms) / 1000:.1f}초 · 평균 {statistics.mean(ms) / 1000:.1f}초")
    print(f"판단 못 함(네트워크·응답 없음) {sum(r['decision'] == 'none' for r in dec)}번")
    print()
    if ver:
        print(f"확인하기 {len(ver)}번: " + ", ".join(f"{r['n']}번 {r['result']}" for r in ver))
        if vms:
            print(f"확인 한 번 걸린 시간 중앙값 {statistics.median(vms) / 1000:.1f}초")
    if top:
        print("도움이 올라간 카드: " + ", ".join(f"{k}번 {lv_name.get(v, v)}까지" for k, v in sorted(top.items())))
    print()
    print("데모에 쓸 한 줄(영상과 대조한 뒤에만):")
    print(f'  "Live Coach: {len(entered_auto)} of {max(n - 1, 0)} card changes made automatically and kept; median decision {statistics.median(ms) / 1000:.1f} s"' if ms else "  (판단 기록 없음)")
    if undone:
        print("\n되돌린 자동 넘김(영상에서 그 시각을 확인):")
        for a in undone:
            print(f"  +{a['t'] - start['t']:.0f}초  {a['cur']}번 → {a['to']}번")


if __name__ == "__main__":
    main()
