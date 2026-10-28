# 첫 실험: Muse Spark가 영상을 어떤 형태로 받는지, 1회 비용·응답 시간은 얼마인지
import base64, json, os, sys, time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1", max_retries=1, timeout=180)
MODEL = "muse-spark-1.3"
RUN = Path("runs/exp1")
PRICE_IN, PRICE_OUT = 1.25 / 1e6, 4.25 / 1e6  # 달러/토큰

PROMPT = """This is a 30-second clip of an adult making a latte.
Split it into steps, one physical action per step.
Return only JSON: {"steps":[{"start":sec,"end":sec,"rep":sec,"sentence":"short plain sentence, one action","object":"thing in hand"}]}
Times are seconds from the start of the clip."""


def b64(path):
    return base64.b64encode(Path(path).read_bytes()).decode()


def content_file():
    f = client.files.create(file=open(RUN / "clip30.mp4", "rb"), purpose="user_data")
    return [{"type": "input_file", "file_id": f.id}, {"type": "input_text", "text": PROMPT}]


def content_inline():
    return [{"type": "input_video", "video_url": "data:video/mp4;base64," + b64(RUN / "clip30.mp4")},
            {"type": "input_text", "text": PROMPT}]


def content_frames():
    parts = []
    for i, p in enumerate(sorted((RUN / "frames").glob("*.jpg"))):
        parts.append({"type": "input_text", "text": f"t={i}s"})
        parts.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + b64(p)})
    return parts + [{"type": "input_text", "text": PROMPT}]


def attempt(name, build):
    t0 = time.time()
    try:
        r = client.responses.create(model=MODEL, input=[{"role": "user", "content": build()}], store=False)
    except Exception as e:
        print(f"[{name}] 실패 {time.time() - t0:.1f}s: {type(e).__name__}: {str(e)[:300]}")
        return
    dt = time.time() - t0
    u = r.usage
    cost = u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT
    (RUN / f"{name}.txt").write_text(r.output_text)
    print(f"[{name}] 성공 {dt:.1f}s  입력 {u.input_tokens} / 출력 {u.output_tokens} 토큰  ≈ ${cost:.4f}")
    print(r.output_text[:1500])


for name in sys.argv[1:] or ["file", "inline", "frames"]:
    attempt(name, {"file": content_file, "inline": content_inline, "frames": content_frames}[name])
