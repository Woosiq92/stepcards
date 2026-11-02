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
while t < dur and cur <= len(cards):
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

ends = {c["n"]: c["end"] for c in cards}
rows = []
for m in moves:
    if m["to"] == "end":
        rows.append({"to": "end", "vt": m["vt"], "lag": round(m["vt"] - ends[len(cards)], 1)}); continue
    rows.append({"to": m["to"], "vt": m["vt"], "lag": round(m["vt"] - ends[m["to"] - 1], 1)})  # n번으로 넘어간 시각 - (n-1)번 단계 끝
reached = max([m["to"] for m in moves if m["to"] != "end"] or [1])
lags = [r["lag"] for r in rows if r["to"] != "end"]
early = [r for r in rows if r["lag"] < -2]  # 앞 단계가 끝나기 2초 넘게 전에 넘김 = 잘못 넘김
summary = {"run": a.run, "states": a.states, "speed": a.speed, "variant": a.variant, "live": a.live, "cards": len(cards), "reached": reached,
           "finished": any(m["to"] == "end" for m in moves), "moves": rows,
           "lag_median": sorted(lags)[len(lags) // 2] if lags else None, "lag_max": max(lags) if lags else None, "early": len(early),
           "calls": len(log), "cost": round(cost, 3)}
print(json.dumps(summary, ensure_ascii=False))
if a.out:
    Path(a.out).write_text(json.dumps({"summary": summary, "log": log}, ensure_ascii=False, indent=1))
