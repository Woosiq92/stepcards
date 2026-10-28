# 실험 2: 전체 영상을 1초 사진 묶음으로 여러 번 돌려 결과가 얼마나 흔들리는지 본다
import base64, json, os, subprocess, sys, time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1", max_retries=1, timeout=300)
MODEL = "muse-spark-1.3"
RUN = Path(sys.argv[2] if len(sys.argv) > 2 else "runs/exp2")  # 실험 4: runs/exp4 = 자막 가린 사진
FRAMES = RUN / "frames"
PRICE_IN, PRICE_OUT = 1.25 / 1e6, 4.25 / 1e6

PROMPT = """These are frames taken once per second from a video of an adult making a drink. Each frame is preceded by its time t in seconds.
Split the video into steps a learner would follow, one physical action per step. Skip intro/outro shots with no action.
Return only JSON: {"steps":[{"start":sec,"end":sec,"rep":sec,"ko":"쉬운 한국어 한 문장, 동작 하나","en":"short plain English, one action","object":"thing in the hand"}]}"""

if not FRAMES.exists():
    FRAMES.mkdir(parents=True)
    subprocess.run(["ffmpeg", "-v", "error", "-i", "samples/latte.mp4", "-vf", "fps=1,scale=-2:360", "-q:v", "6",
                    str(FRAMES / "f%03d.jpg")], check=True)

content = []
for i, p in enumerate(sorted(FRAMES.glob("*.jpg"))):
    content.append({"type": "input_text", "text": f"t={i}s"})
    content.append({"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode()})
content.append({"type": "input_text", "text": PROMPT})

for n in range(1, int(sys.argv[1] if len(sys.argv) > 1 else 3) + 1):
    t0 = time.time()
    r = client.responses.create(model=MODEL, input=[{"role": "user", "content": content}], store=False)
    dt = time.time() - t0
    u = r.usage
    (RUN / f"run{n}.json").write_text(r.output_text)
    print(f"[run{n}] {dt:.1f}s  입력 {u.input_tokens} / 출력 {u.output_tokens}  ≈ ${u.input_tokens * PRICE_IN + u.output_tokens * PRICE_OUT:.4f}")
    try:
        for s in json.loads(r.output_text.strip().removeprefix("```json").removesuffix("```"))["steps"]:
            print(f"  {s['start']:>3}-{s['end']:<3} rep {s['rep']:<3} {s['ko']}  [{s['object']}]")
    except Exception as e:
        print("  JSON 파싱 실패:", e, r.output_text[:300])
