# 따라 하기 모의 시험: 영상을 카메라 대신 흘려보내며, 카드가 제때 넘어가는지·응답 시간·1분당 비용을 잰다
# 사용: .venv/bin/python coach_sim.py <실행 폴더 id> [확인 간격 초=2] [사진 수=4]
import base64, json, sys
from pathlib import Path
import coach

run = Path("runs") / sys.argv[1]
every = float(sys.argv[2]) if len(sys.argv) > 2 else 2
k = int(sys.argv[3]) if len(sys.argv) > 3 else 4
cards = json.loads((run / "cards.json").read_text())["cards"]
frames = sorted((run / "frames").glob("*.jpg"))
url = lambda i: "data:image/jpeg;base64," + base64.b64encode(frames[i].read_bytes()).decode()

t, cur, log, total, lat, prev = float(cards[0]["start"]), 1, [], 0.0, [], 0
while t < len(frames) - 1 and cur <= len(cards):
    i = int(t)
    r = coach.check(cards, cur, [url(j) for j in range(max(0, i - k + 1), i + 1)], prev)
    prev = r["seen"]
    total += r["cost"]; lat.append(r["latency"])
    t += max(every, r["latency"])  # 판단하는 동안에도 영상은 흘러간다
    if r["decision"] != "wait":
        log.append((round(t), cur, r["decision"], r["seen"], r["current_done"], r["sam"]))
    if r["decision"] == "next":
        nxt = cards[cur]  # 다음 카드(0부터 cur)
        print(f"{t:6.1f}s  {cur}→{cur + 1}  (다음 카드 시작 {nxt['start']}s, 차이 {t - nxt['start']:+.0f}s)  seen={r['seen']} done={r['current_done']} sam={r['sam']}")
        cur += 1
        if cur == len(cards):
            break
    elif r["decision"] == "jump":
        print(f"{t:6.1f}s  {cur}→{r['target']} 따라감 (그 카드 시작 {cards[r['target'] - 1]['start']}s)")
        cur, prev = r["target"], 0
        if cur == len(cards):
            break
    elif r["decision"] == "again":
        print(f"{t:6.1f}s  다시 보여 주기(현재 {cur}, 본 단계 {r['seen']})")
dur = t - cards[0]["start"]
print(f"\n도달 카드 {cur}/{len(cards)} · 판단 {len(lat)}회 · 평균 응답 {sum(lat) / len(lat):.1f}s(최대 {max(lat):.1f}) · 비용 ${total:.3f} · 1분당 ${total / dur * 60:.3f}")
