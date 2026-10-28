import base64, json, time, statistics
from pathlib import Path
import pipeline
run = Path("runs/9ba0bf565609"); cards = json.loads((run / "cards.json").read_text())["cards"]
frames = sorted((run / "frames").glob("*.jpg"))
url = lambda i: "data:image/jpeg;base64," + base64.b64encode(frames[i].read_bytes()).decode()
def call(nf, window, t=100, cur=11):
    lo, hi = (max(1, cur - 1), min(len(cards), cur + 3)) if window else (1, len(cards))
    steps = "\n".join(f"{i}. {cards[i-1]['en']}" for i in range(lo, hi + 1))
    content = []
    for k, i in enumerate(range(t - nf + 1, t + 1)):
        content += [{"type": "input_image", "image_url": url(i)}]
    content.append({"type": "input_text", "text": f"Steps:\n{steps}\nThe learner is on step {cur}. Images: last {nf} seconds, oldest first. Answer only JSON {{\"seen\": step number in the latest image or 0, \"current_done\": bool}}."})
    t0 = time.time(); r = pipeline.client.responses.create(model="muse-spark-1.3", input=[{"role": "user", "content": content}], store=False)
    return time.time() - t0, r.usage.output_tokens, r.output_text.strip()[:60]
for nf, window in [(4, False), (4, True), (2, True), (1, True)]:
    res = [call(nf, window) for _ in range(3)]
    print(f"사진 {nf}장 · 목록 {'앞뒤만' if window else '전체'}: 응답 {statistics.median(r[0] for r in res):.1f}s(중앙값) · 출력 토큰 {[r[1] for r in res]} · {res[0][2]}")
