import base64, json, time, statistics
from pathlib import Path
import pipeline
run = Path("runs/9ba0bf565609"); cards = json.loads((run / "cards.json").read_text())["cards"]
frames = sorted((run / "frames").glob("*.jpg"))
url = lambda i: "data:image/jpeg;base64," + base64.b64encode(frames[i].read_bytes()).decode()
steps = "\n".join(f"{i}. {c['en']}" for i, c in enumerate(cards, 1))
def call(t, cur, **kw):
    content = [{"type": "input_image", "image_url": url(i)} for i in (t - 1, t)]
    content.append({"type": "input_text", "text": f"Steps:\n{steps}\nThe learner is on step {cur}. Images: last 2 seconds. Answer only JSON {{\"seen\": step number in the latest image or 0, \"current_done\": bool}}."})
    t0 = time.time(); r = pipeline.client.responses.create(model="muse-spark-1.3", input=[{"role": "user", "content": content}], store=False, **kw)
    return time.time() - t0, r.usage.output_tokens, r.output_text.strip()[:50]
for name, kw in [("기본", {}), ("effort=low", {"reasoning": {"effort": "low"}}), ("effort=minimal", {"reasoning": {"effort": "minimal"}}), ("effort=none", {"reasoning": {"effort": "none"}})]:
    try:
        res = [call(100, 11, **kw) for _ in range(3)]
        print(f"{name}: {statistics.median(r[0] for r in res):.1f}s · 토큰 {[r[1] for r in res]} · {res[0][2]}")
    except Exception as e:
        print(name, "실패", str(e)[:150])
