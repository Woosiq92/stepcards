# 따라 하기 자동 넘김 측정기: 영상을 카메라처럼 흘려(브라우저와 같은 480px·0.5초 간격, 판단 사이 0.4초) 실제 coach.check 를 부르고
# 카드마다 넘어간 시각을 시범의 단계 끝과 비교한다. 판단에 걸린 실제 시간만큼 영상 시계를 진행시킨다(실시간과 같은 조건)
# 사용: .venv/bin/python coach_eval.py <실행 id> <영상> [--speed 1.0] [--variant none|zoom|dim] [--live] [--out 결과.json]
import argparse, base64, json, subprocess, tempfile, time
from pathlib import Path
import coach

ap = argparse.ArgumentParser()
ap.add_argument("run"); ap.add_argument("video")
ap.add_argument("--speed", type=float, default=1.0)  # 학습자가 시범보다 빠르면(>1) / 느리면(<1)
ap.add_argument("--variant", default="none")  # 같은 영상을 다른 카메라처럼: zoom(가운데 80% 확대), dim(어둡고 흐림)
ap.add_argument("--live", action="store_true")  # 화면 기본값(실시간 확인 켬)처럼 지금 카드의 끝 사진을 같이 준다
ap.add_argument("--states", action="store_true")  # 11-02 새 방식: 시범의 단계 끝 사진과 맞추기
ap.add_argument("--settle", action="store_true")  # 11-02: 손이 멈춘 순간 한 번 더 묻기(동시에 최대 2개), 화면과 같은 규칙
ap.add_argument("--ends", default="")  # 11-03: 시범이 아닌 시험 영상(생성본 등)의 정답 단계 끝 시각 "11,22,..." — 없으면 cards.json 의 end
ap.add_argument("--wide", action="store_true")  # 11-03 설계 1: 막히면 기준 사진을 전체 단계로 넓힌다(coach.check_states 의 wide)
ap.add_argument("--out", default="")
a = ap.parse_args()

ROOT = Path(__file__).parent
d = ROOT / "runs" / a.run
cards = json.loads((d / "cards.json").read_text())["cards"]
FPS = 4
tmp = Path(tempfile.mkdtemp())
vf = {"none": "", "zoom": "crop=iw*0.8:ih*0.8,", "dim": "eq=brightness=-0.12:contrast=0.8,gblur=sigma=1.2,"}[a.variant]
subprocess.run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"setpts=PTS/{a.speed},{vf}fps={FPS},scale=480:-2", "-q:v", "5", str(tmp / "f%05d.jpg")], check=True)
shots = sorted(tmp.glob("f*.jpg"))
dur = len(shots) / FPS


def shot(t):
    k = min(len(shots) - 1, max(0, int(t * FPS)))
    return "data:image/jpeg;base64," + base64.b64encode(shots[k].read_bytes()).decode()


ref_url = {}
if a.live:
    import verify, pipeline
    ref_url = {c["n"]: pipeline.data_url(verify.reference(d, c, "after")) for c in cards}

t, cur, prev, since, log, moves, pm = 1.0, 1, 0, 0.0, [], [], -1
cost = 0.0
while not a.settle and t < dur and cur <= len(cards):
    if t - since < 0.999:  # 넘긴 뒤에는 사진 2장(1초)이 다시 쌓일 때까지(1.0 과 비교하면 부동소수점 오차로 같은 줄을 영영 돌았다)
        t = since + 1.0
        continue
    frames = [shot(t - 0.5), shot(t)]
    refs = coach.state_refs(d, cards, cur) if a.states else None
    r = coach.check(cards, cur, frames, prev, False, ref_url.get(cards[cur - 1]["n"]) if a.live else None, refs,
                    pm, bool(refs) and coach.change(d, cards, cur) < coach.SIMILAR, (t - since) if since else t)
    lat = r["latency"]; cost += r["cost"]
    log.append({"vt": round(t * a.speed, 1), "cur": cur, **{k: r.get(k) for k in ("decision", "seen", "current_done", "match", "state", "target", "sam")}, "lat": lat})
    t_ans = t + lat
    prev, pm = r["seen"], r.get("done_step", -1)
    to = cur + 1 if r["decision"] == "next" else r["target"] if r["decision"] == "jump" else None
    if to and 1 <= to <= len(cards):
        moves.append({"to": to, "vt": round(t_ans * a.speed, 1)})  # 시범 영상 시각으로
        cur, prev, since = to, 0, t_ans  # pm(끝난 단계 번호)은 넘겨도 그대로
    elif r["decision"] == "finished":
        moves.append({"to": "end", "vt": round(t_ans * a.speed, 1)}); break
    t = t_ans + 0.4

if a.settle:  # 앞의 순차 흉내는 버리고 사건 순서대로 다시: 0.5초마다 사진, 멈춤 감지, 답은 도착 시각 순으로 반영
    from PIL import Image
    small = {}
    def gray(t):
        k = min(len(shots) - 1, max(0, int(t * FPS)))
        if k not in small:
            small[k] = list(Image.open(shots[k]).convert("L").resize((32, 18)).getdata())
        return small[k]
    t, cur, prev, pm, since, log, moves, cost = 1.0, 1, 0, -1, 0.0, [], [], 0.0
    pending, main_next, last, moved = [], 1.0, None, False  # pending = [(도착 시각, 보낸 때 카드, 결과, 주 질문?)]
    ahead = False
    def send(t, main):
        global cost
        frames = [shot(t - 1.5), shot(t - 1.0), shot(t - 0.5), shot(t)]  # 화면과 같이 최근 4장(판단은 보통 뒤 2장만 쓴다)
        on = (t - since) if since else t
        refs = coach.state_refs(d, cards, cur, a.wide and (ahead or coach.stuck(cards, cur, on))) if a.states else None
        r = coach.check(cards, cur, frames, prev, False, None, refs, pm, bool(refs) and coach.change(d, cards, cur) < coach.SIMILAR, (t - since) if since else t)
        cost += r["cost"]
        pending.append((t + r["latency"], cur, r, main))
        log.append({"vt": round(t * a.speed, 1), "cur": cur, "main": main, "nref": len(refs or []), **{k: r.get(k) for k in ("decision", "match", "done_step", "ahead")}, "lat": r["latency"]})
    while t < dur and cur <= len(cards):
        for item in sorted([p for p in pending if p[0] <= t], key=lambda p: p[0]):  # 도착한 답
            pending.remove(item)
            at_t, c0, r, main = item
            if main:
                main_next = at_t + 0.4
            if c0 != cur:
                continue  # 그 사이 카드가 바뀌었으면 버린다(화면과 같음)
            prev, pm, ahead = r["seen"], r.get("done_step", -1), bool(r.get("ahead"))
            to = cur + 1 if r["decision"] == "next" else r["target"] if r["decision"] == "jump" else None
            if to and 1 <= to <= len(cards):
                moves.append({"to": to, "vt": round(at_t * a.speed, 1)}); cur, prev, since = to, 0, at_t
            elif r["decision"] == "finished":
                moves.append({"to": "end", "vt": round(at_t * a.speed, 1)}); cur = len(cards) + 1
        if cur > len(cards):
            break
        g = gray(t)
        if last is not None:
            m = sum(abs(x - y) for x, y in zip(g, last)) / len(g)
            if m >= 4:
                moved = True
            elif m < 2 and moved:
                moved = False
                if len(pending) < 2 and t - since >= 0.999:
                    send(t, False)
        last = g
        if not any(p[3] for p in pending) and t >= main_next and t - since >= 0.999:
            send(t, True)
        t = round(t + 0.5, 3)

ends = {c["n"]: c["end"] for c in cards}
if a.ends:
    ends = {i + 1: float(x) for i, x in enumerate(a.ends.split(","))}
rows = []
for m in moves:
    if m["to"] == "end":
        rows.append({"to": "end", "vt": m["vt"], "lag": round(m["vt"] - ends[len(cards)], 1)}); continue
    rows.append({"to": m["to"], "vt": m["vt"], "lag": round(m["vt"] - ends[m["to"] - 1], 1)})  # n번으로 넘어간 시각 - (n-1)번 단계 끝
reached = max([m["to"] for m in moves if m["to"] != "end"] or [1])
lags = [r["lag"] for r in rows if r["to"] != "end"]
early = [r for r in rows if r["lag"] < -2]  # 앞 단계가 끝나기 2초 넘게 전에 넘김 = 잘못 넘김
summary = {"run": a.run, "states": a.states, "settle": a.settle, "speed": a.speed, "variant": a.variant, "live": a.live, "cards": len(cards), "reached": reached,
           "finished": any(m["to"] == "end" for m in moves), "moves": rows,
           "lag_median": sorted(lags)[len(lags) // 2] if lags else None, "lag_max": max(lags) if lags else None, "early": len(early),
           "calls": len(log), "cost": round(cost, 3),
           "stuck_max": round(max(b - a_ for a_, b in zip([0.0] + [m["vt"] for m in moves], [m["vt"] for m in moves] + [dur * a.speed])), 1)}  # 한 카드에 가장 오래 머문 시간
print(json.dumps(summary, ensure_ascii=False))
if a.out:
    Path(a.out).write_text(json.dumps({"summary": summary, "log": log}, ensure_ascii=False, indent=1))
