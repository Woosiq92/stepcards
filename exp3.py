# 실험 3: SAM 3.1이 대표 사진에서 컵·우유·숟가락을 잡는지, 표현을 바꾸면 달라지는지
import base64, os, re, time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw

load_dotenv()
client = OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1", max_retries=1, timeout=120)
RUN = Path("runs/exp3")
PROMPTS = ["cup", "clear glass cup", "milk", "white liquid", "spoon", "long thin stick held in hand"]
COLORS = ["red", "orange", "blue", "cyan", "lime", "magenta"]
BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+)")

for img in sorted(RUN.glob("t*.jpg")):
    if "_sam" in img.name:
        continue
    url = "data:image/jpeg;base64," + base64.b64encode(img.read_bytes()).decode()
    pic = Image.open(img).convert("RGB")
    draw = ImageDraw.Draw(pic)
    line = []
    for prompt, color in zip(PROMPTS, COLORS):
        t0 = time.time()
        try:
            r = client.responses.create(model="sam-3.1", input=[{"role": "user", "content": [
                {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": url}]}], store=False)
        except Exception as e:
            line.append(f"{prompt}: 오류 {str(e)[:120]}")
            continue
        boxes = [tuple(map(int, m)) for m in BOX.findall(r.output_text or "")]
        for b in boxes:
            draw.rectangle(b, outline=color, width=4)
            draw.text((b[0] + 4, b[1] + 4), prompt, fill=color)
        line.append(f"{prompt}: {len(boxes)}개 ({time.time() - t0:.1f}s)")
        if img.name == "t14.jpg" and prompt == "cup":
            print("  원문 예시:", (r.output_text or "")[:200])
    pic.save(RUN / f"{img.stem}_sam.jpg", quality=80)
    print(img.name, pic.size, " | ".join(line))
