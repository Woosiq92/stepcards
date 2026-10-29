# 영상 → 단계 카드 파이프라인 ①~④
# 사용: .venv/bin/python pipeline.py 영상.mp4 [--fresh]
import base64, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import requests
from PIL import Image, ImageDraw
from check import check

load_dotenv(Path(__file__).parent / ".env")
client = OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url="https://api.meta.ai/v1", max_retries=2, timeout=300)
STEP_MODEL, SAM_MODEL, ASR_MODEL = "muse-spark-1.3", "sam-3.1", "muse-voice-transcribe-1.0"
ASR_PRICE = 0.18 / 3600  # 달러/초
PRICE_IN, PRICE_OUT = 1.25 / 1e6, 4.25 / 1e6
MAX_RETRY = 2
BOX = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+)")

PROMPT = """These are frames taken once per second from a video of an adult doing a task with their hands. Each frame is preceded by its time t in seconds. The video is {duration} seconds long.
Split the video into steps a learner would follow. Skip intro/outro shots with no action.
Rules:
- Only steps a learner must do. No steps for showing things to the camera, looking around, or talking.
- If the person waits more than about 5 seconds for a machine or process (grinding, brewing, steaming, heating), make that a step too, e.g. "샷이 다 나올 때까지 기다리세요."
- One physical action per step. "ko" is one short plain Korean sentence with one verb, at most 25 characters, ending with "~세요" (e.g. "우유를 부으세요."; no "~하고 ~하세요").
- "en" is the same action in short plain English.
- start and end are whole seconds, end inclusive. Each step starts after the previous step's end. start <= rep <= end.
- rep is a second in the middle of the action where the hand is on the object (not after the action has finished).
- "object" is the main thing in the hand, in short English words (e.g. "small glass pitcher").
- "look" describes only how that object looks, without its name: shape, color, material (e.g. "thin silver rod with a round tip").
Return only JSON: {{"steps":[{{"start":0,"end":0,"rep":0,"ko":"","en":"","object":"","look":""}}]}}"""


class Run:
    def __init__(self, video):
        self.video = Path(video).resolve()
        digest = hashlib.sha256(self.video.read_bytes()).hexdigest()[:12]
        self.dir = Path(__file__).parent / "runs" / digest
        self.dir.mkdir(parents=True, exist_ok=True)
        self.progress = self.dir / "progress.json"
        self.events = json.loads(self.progress.read_text())["events"] if self.progress.exists() else []

    def log(self, stage, msg, **extra):
        self.events.append({"t": round(time.time(), 1), "stage": stage, "msg": msg, **extra})
        self.progress.write_text(json.dumps({"video": self.video.name, "video_path": str(self.video), "events": self.events}, ensure_ascii=False, indent=1))
        print(f"[{stage}] {msg}")

    def path(self, name):
        return self.dir / name


def data_url(path):
    return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def parse_json(text):
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    return json.loads(text)["steps"]


# ① 영상 길이 + 1초 사진
def extract(run):
    duration = int(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                         str(run.video)], capture_output=True, text=True, check=True).stdout))
    frames = run.path("frames")
    if not frames.exists():
        frames.mkdir()
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(run.video), "-vf", "fps=1,scale=-2:360", "-q:v", "6",
                        str(frames / "f%03d.jpg")], check=True)
    run.log("extract", f"영상 {duration}초, 사진 {len(list(frames.glob('*.jpg')))}장")
    return duration, sorted(frames.glob("*.jpg"))


# ①-2 영상 속 말 받아쓰기(Muse Voice Transcribe). 말이 없으면 빈 목록
def listen(run):
    out = run.path("speech.json")
    if out.exists():
        return json.loads(out.read_text())
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0",
                                str(run.video)], capture_output=True, text=True).stdout.strip()
    turns = []
    if has_audio:
        wav = run.path("audio.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(run.video), "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le",
                        "-map_metadata", "-1", "-t", "600", str(wav)], check=True)  # API는 10분까지
        req = {"mode": "ENDPOINTING", "model": ASR_MODEL, "audioEncoding": "WAV", "languageBias": ["Korean", "English"]}
        r = requests.post("https://api.meta.ai/v1/asr/transcribe", headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
                          files={"request": (None, json.dumps(req), "application/json"), "audio": ("audio.wav", wav.open("rb"), "audio/wav")},
                          timeout=300)
        r.raise_for_status()
        data = r.json()
        turns = [{"start": t["startMs"] / 1000, "end": t["endMs"] / 1000, "text": t["transcript"].strip()}
                 for t in data.get("turns", []) if t.get("transcript", "").strip()]
        cost = data.get("audioDurationMs", 0) / 1000 * ASR_PRICE
        run.log("listen", f"말 {len(turns)}구간 받아씀" if turns else "영상에 말소리가 없음", n=len(turns), cost=round(cost, 4))
    else:
        run.log("listen", "영상에 소리가 없음", n=0)
    out.write_text(json.dumps(turns, ensure_ascii=False, indent=1))
    return turns


# ②-1 "더 가까이 보기" 도구: 경계가 애매하면 모델이 스스로 그 구간을 1초에 4장으로 다시 본다
LOOK_MAX_CALLS, LOOK_MAX_SPAN, LOOK_FPS = 6, 8, 2
LOOK_TOOL = {"type": "function", "name": "look_closer",
             "description": f"See {LOOK_FPS} frames per second for a short part of the video (at most {LOOK_MAX_SPAN} seconds). "
                            "Use it when you are unsure where a step starts or ends, or when a short action may hide between the 1-second frames.",
             "parameters": {"type": "object", "additionalProperties": False, "required": ["start", "end"],
                            "properties": {"start": {"type": "number"}, "end": {"type": "number"}}}}
LOOK_HINT = (f"You may call look_closer up to {LOOK_MAX_CALLS} times before answering if a boundary is unclear. "
             "Then answer with the JSON only.")


def look_closer(run, start, end):
    start = max(0.0, float(start))
    end = min(start + LOOK_MAX_SPAN, max(start + 0.5, float(end)))
    out = run.path(f"look/{start:.1f}-{end:.1f}")
    if not out.exists():
        out.mkdir(parents=True)
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(start), "-t", str(end - start), "-i", str(run.video),
                        "-vf", f"fps={LOOK_FPS},scale=-2:360", "-q:v", "6", str(out / "f%03d.jpg")], check=True)
    parts = []
    for k, f in enumerate(sorted(out.glob("*.jpg"))):
        parts += [{"type": "input_text", "text": f"t={start + k / LOOK_FPS:.2f}s"}, {"type": "input_image", "image_url": data_url(f)}]
    return start, end, parts


def ask_steps(run, content, look):
    """단계 JSON 요청. look이면 look_closer 도구를 주고, 모델이 부르면 사진을 붙여 다시 묻는다(최대 LOOK_MAX_CALLS번)."""
    messages = [{"role": "user", "content": content + ([{"type": "input_text", "text": LOOK_HINT}] if look else [])}]
    cost, calls = 0.0, 0
    for _ in range(LOOK_MAX_CALLS + 4):  # Meta API는 tool_choice "auto"만 받아서, 한도를 넘으면 도구 대신 "지금 답하라"를 돌려준다
        kw = {"tools": [LOOK_TOOL]} if look else {}
        r = client.responses.create(model=STEP_MODEL, input=messages, store=False, **kw)
        cost += r.usage.input_tokens * PRICE_IN + r.usage.output_tokens * PRICE_OUT
        fcs = [o for o in r.output if o.type == "function_call"]
        if not fcs:
            return r.output_text, cost
        messages += [o.model_dump(exclude_none=True) for o in r.output if o.type in ("function_call", "reasoning")]
        for fc in fcs:
            if calls >= LOOK_MAX_CALLS:
                messages.append({"type": "function_call_output", "call_id": fc.call_id,
                                 "output": "No more looks are available. Answer now with the JSON only."})
                continue
            args = json.loads(fc.arguments or "{}")
            start, end, parts = look_closer(run, args.get("start", 0), args.get("end", 0))
            calls += 1
            run.log("look", f"{start:.1f}~{end:.1f}초를 1초에 {LOOK_FPS}장으로 다시 봄", start=start, end=end)
            messages.append({"type": "function_call_output", "call_id": fc.call_id,
                             "output": f"{len(parts) // 2} frames from {start:.1f}s to {end:.1f}s are in the next message."})
            messages.append({"role": "user", "content": parts})
    raise RuntimeError("look_closer 반복이 끝나지 않음")


# ②③ 단계 나누기 + 검사, 걸리면 이유를 붙여 다시
def split_steps(run, duration, frames, speech=(), look=False, every=1):
    """every>1이면 every초 간격의 거친 사진만 주고, 경계는 look_closer로 확대해 찾게 한다."""
    content = []
    for i, p in enumerate(frames[::every]):
        content += [{"type": "input_text", "text": f"t={i * every}s"}, {"type": "input_image", "image_url": data_url(p)}]
    if every > 1:
        content.append({"type": "input_text", "text": f"These overview frames are {every} seconds apart, so short steps and exact boundaries "
                        f"are not visible. Use look_closer on each part where a step starts or ends to get exact times."})
    if speech:  # 동작·시간은 사진으로, 양·재료 이름은 말에서
        lines = "\n".join(f"[{t['start']:.1f}-{t['end']:.1f}s] {t['text']}" for t in speech)
        content.append({"type": "input_text", "text": "What the person said while doing it (times in seconds). Decide actions and times "
                        "from the frames; use the speech for ingredient and tool names. If an amount is said for a step, put it in "
                        "that step's ko and en sentence (e.g. \"우유 100ml를 부으세요.\", \"Pour 100ml of milk.\"):\n" + lines})
    content.append({"type": "input_text", "text": PROMPT.format(duration=duration)})

    feedback, steps, problems, warnings = None, None, [], []
    for attempt in range(1 + MAX_RETRY):
        ask = content if feedback is None else content + [{"type": "input_text", "text": feedback}]
        t0 = time.time()
        text, cost = ask_steps(run, ask, look)
        run.path(f"steps_try{attempt + 1}.txt").write_text(text)
        try:
            steps = parse_json(text)
            problems, warnings = check(steps, duration)
        except (ValueError, KeyError, TypeError) as e:
            steps, problems, warnings = None, [f"JSON 형식이 아닙니다: {e}"], []
        run.log("split", f"{attempt + 1}번째 시도: 단계 {len(steps or [])}개, 문제 {len(problems)}개 ({time.time() - t0:.0f}초, ${cost:.3f})",
                n=len(steps or []), problems=problems, warnings=warnings, cost=round(cost, 4))
        if not problems:
            break
        feedback = ("Your previous answer had these problems. Fix them and return the full JSON again.\n- "
                    + "\n- ".join(problems) + "\nPrevious answer:\n" + text)
    status = "ok" if not problems else "needs_review"
    if status == "needs_review":
        run.log("split", "다시 시도해도 남은 문제가 있어 사람 확인 필요로 표시")
    return {"status": status, "problems": problems, "warnings": warnings, "steps": steps or []}


# ④ 대표 사진 + SAM 강조(손과 겹치는 물건 상자를 고름)
def sam_boxes(image, prompt):
    """image는 파일 경로 또는 data URL(따라 하기 모드의 카메라 사진)."""
    url = image if str(image).startswith("data:") else data_url(image)
    r = client.responses.create(model=SAM_MODEL, store=False, input=[{"role": "user", "content": [
        {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": url}]}])
    return [tuple(map(int, m)) for m in BOX.findall(r.output_text or "")]


# 사진 → 그림 카드(Muse Image 편집). 웹·이미지 검색은 꺼서 카드 사진이 검색에 쓰이지 않게 한다
ILL_PROMPT = ("Redraw this photo as a simple picture-instruction card illustration for learners with intellectual disabilities. "
              "Keep exactly the same action, hand positions and objects{obj}. Plain pure white background, remove clutter, "
              "thick black outlines of even width, flat colors, no text, no logos or brand marks, no extra objects. "
              # 카드마다 따로 그리면 피부색·배경이 제각각이라(냅킨 12장) 모든 카드에 같은 값을 박는다
              "Same style on every card: hands always drawn with one medium skin tone (#D9A27A), no shading or gradients.")


def illustrate(image, obj=""):
    """카드 사진 → 그림(jpeg 바이트). $0.01/장, 8~9초(runs/exp6)."""
    r = requests.post("https://api.meta.ai/v1/images/edits", timeout=300,
                      headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}", "Content-Type": "application/json"},
                      json={"model": "muse-image-1.0", "n": 1, "output_format": "jpeg", "reasoning_strength": "low",
                            "prompt": ILL_PROMPT.format(obj=f"; the {obj} in the hand must stay clearly visible" if obj else ""),
                            "images": [{"image_url": data_url(image)}],
                            "tool_enablement": {"enable_image_search": False, "enable_web_search": False, "enable_shell": False}})
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


def overlap(a, b):
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def grab(video, t, out):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=-2:720", "-q:v", "3", str(out)], check=True)


def find_box(img, s):
    """이름 → 생김새 → 이름 마지막 단어 순으로 찾고, 손과 가장 많이 겹치는 상자를 고른다."""
    hands = sam_boxes(img, "hand")
    words = (s.get("object") or "").split()
    names = [s.get("object", ""), s.get("look", ""), words[-1] if words else ""]
    for prompt in dict.fromkeys(p for p in names if p):  # 사람이 추가한 빈 카드는 이름이 없을 수 있음
        found = sam_boxes(img, prompt)
        if found:
            box = max(found, key=lambda b: max((overlap(b, h) for h in hands), default=0))
            return box, prompt, any(overlap(box, h) for h in hands)
    return None, None, False


def highlight(run, steps):
    cards_dir = run.path("cards")
    cards_dir.mkdir(exist_ok=True)
    cards = []
    for i, s in enumerate(steps, 1):
        img = cards_dir / f"{i:02d}.jpg"
        # 대표 시각 → 구간 1/4·1/2·3/4 지점. 손과 물건이 겹치는 첫 사진을 쓴다
        times = list(dict.fromkeys([s["rep"]] + [round(s["start"] + (s["end"] - s["start"]) * k / 4) for k in (1, 2, 3)]))
        best = None
        for t in times:
            tmp = cards_dir / f"{i:02d}_t{t}.jpg"
            grab(run.video, t, tmp)
            box, used, touch = find_box(tmp, s)
            if best is None or (box and not best[1]) or (touch and not best[3]):
                best = (t, box, used, touch, tmp)
            if touch:
                break
        t, box, used, touch, tmp = best
        tmp.replace(img)
        for f in cards_dir.glob(f"{i:02d}_t*.jpg"):
            f.unlink()
        if box:
            pic = Image.open(img).convert("RGB")
            ImageDraw.Draw(pic).rectangle(box, outline=(255, 140, 0), width=6)
            pic.save(cards_dir / f"{i:02d}_hl.jpg", quality=85)
        cards.append({**s, "n": i, "image": f"cards/{i:02d}.jpg", "frame_t": t, "box": box, "box_prompt": used, "box_touches_hand": touch})
        moved = f", 사진 {s['rep']}→{t}초" if t != s["rep"] else ""
        run.log("highlight", f"{i}단계 '{s['object']}': " + (f"상자 찾음({used}, 손과 {'겹침' if touch else '안 겹침'}{moved})" if box else f"못 찾음{moved}"), i=i, total=len(steps))
    return cards


def main(video, fresh=False, look=False):
    run = Run(video)
    run.events = []  # 진행판은 이번 실행만 보여 준다
    run.log("start", f"{run.video.name} → {run.dir.name}")
    try:
        build(run, fresh, look)
    except Exception as e:
        run.log("error", f"멈췄어요: {type(e).__name__}: {str(e)[:200]}")
        raise


def build(run, fresh, look=False):
    duration, frames = extract(run)
    speech = listen(run)
    steps_file = run.path("steps.json")
    if steps_file.exists() and not fresh:
        result = json.loads(steps_file.read_text())
        run.log("split", "저장된 단계 사용(캐시)")
    else:
        result = split_steps(run, duration, frames, speech, look)
        steps_file.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    cards_file = run.path("cards.json")
    if cards_file.exists() and not fresh:
        run.log("highlight", "저장된 카드 사용(캐시)")
    else:
        cards = highlight(run, result["steps"])
        cards_file.write_text(json.dumps({"duration": duration, "status": result["status"], "problems": result["problems"],
                                          "warnings": result["warnings"], "cards": cards}, ensure_ascii=False, indent=1))
    run.log("done", f"완료: {run.dir}")


if __name__ == "__main__":
    main(sys.argv[1], fresh="--fresh" in sys.argv, look="--look" in sys.argv)
