# 데모 영상 합치기: 설명 화면 + 녹화 장면 + 영어 내레이션(합성 음성) + 자막 → demo/out/stepcards_demo.mp4
# 사용: .venv/bin/python demo/compose.py <만들기 실행 id>
import json, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "out"
TMP = OUT / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
RUN = ROOT / "runs" / sys.argv[1]
W, H = 1920, 1080
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BG, INK, MUTED, ACCENT = (246, 244, 239), (29, 29, 27), (111, 108, 102), (224, 122, 31)


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=6 if bold else 0)  # 6 = Bold


def sh(*args):
    subprocess.run(list(map(str, args)), check=True)


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True, check=True).stdout)


# 실제로 잰 숫자만 쓴다: 이번 만들기 실행의 기록에서 계산
prog = json.loads((RUN / "progress.json").read_text())["events"]
cards = json.loads((RUN / "cards.json").read_text())["cards"]
make_min = (prog[-1]["t"] - prog[0]["t"]) / 60
make_cost = sum(e.get("cost", 0) for e in prog)
video_sec = next(int(m.group(1)) for e in prog if (m := re.search(r"영상 (\d+)초", e["msg"])))

# 이번 실행에서 실제로 일어난 일만 말한다
splits = [e for e in prog if e["stage"] == "split" and "n" in e]
if len(splits) > 1 and not splits[-1]["problems"]:
    RUN_NOTE = "In this run, the first answer broke a rule. The checker sent back the reason, and the next answer passed. "
elif splits and not splits[-1]["problems"]:
    RUN_NOTE = "In this run, every step passed the checks on the first try. "
else:
    RUN_NOTE = "In this run, a few issues were left for the teacher to check. "

SEGMENTS = [
    ("slide_title", None,
     "StepCards. Special-education teachers turn every job skill into picture cards by hand: film, pause, screenshot, write, print. "
     "We turn one demonstration video into checked step cards."),
    ("clip_input", None,
     "A worker shows the task once, filmed first-person, the way smart glasses would see it. "
     "Here a public first-person video stands in, with spoken Korean added by a synthetic voice."),
    ("making", "making_all.mp4",
     "We drop in the video. Muse Voice Transcribe writes down what was said. "
     "Muse Spark splits the video into one-action steps, with times and plain Korean and English sentences. "
     "Code checks every step: overlapping times, long sentences, two actions in one card, even Korean spelling. "
     + RUN_NOTE +
     "Then SAM 3.1 outlines the object in the worker's hand."),
    ("edit", "edit.mp4",
     "The teacher stays in charge. Every edit saves and is checked again. "
     "Put two actions in one sentence, and the card turns red with a plain-language note. Split it, and it passes. "
     "A better photo is one click away."),
    ("use", "use.mp4",
     "Cards print six to an A4 page, or play one at a time on a tablet."),
    ("coach", "coach.mp4",
     "Coach mode closes the loop. The cards from one demonstration become the guide for the learner. "
     "Muse Spark sees which step is happening, and SAM confirms the object in hand before the next card appears. "
     "No praise, no scores, nothing recorded. In this clip, a recorded video plays the role of the camera."),
    ("slide_close", None,
     "Every model here is Meta's: Muse Spark, SAM 3.1 and Muse Voice Transcribe. "
     "Next: film and coach through Ray-Ban Meta glasses, send cards over WhatsApp, "
     "and run open-weight Muse Spark inside schools, so student video never leaves the building."),
    ("slide_credits", None, ""),
]

CROP = {"making": "crop=1280:720:160:0,", "edit": "crop=1280:720:160:0,"}  # 앱 내용이 있는 가운데만 키워서 글자가 읽히게
MAX_SPEED = {"making": 3.0, "edit": 1.5, "use": 1.5, "coach": 3.0}

LABELS = {  # 화면 위쪽 작은 표시
    "clip_input": "Sample input · CC BY video by Cornffy · synthetic Korean narration added",
    "making": f"Real run · {video_sec // 60} min {video_sec % 60} s video",
    "coach": "Coach mode · recorded video used in place of a live camera",
}


def slide(name, lines):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    y = 230
    for text, size, bold, color in lines:
        d.text((160, y), text, font=font(size, bold), fill=color)
        y += int(size * 1.55)
    p = TMP / f"{name}.png"
    img.save(p)
    return p


def caption_png(text, i):
    img = Image.new("RGBA", (W, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(38)
    words, rows, row = text.split(), [], ""
    for w in words:  # 두 줄 안에서 줄바꿈
        if d.textlength(row + " " + w, font=f) > W - 360 and row:
            rows.append(row); row = w
        else:
            row = (row + " " + w).strip()
    rows.append(row)
    rows = rows[-2:]
    h = 56 * len(rows) + 30
    d.rounded_rectangle(((W - max(d.textlength(r, font=f) for r in rows)) / 2 - 30, 150 - h - 10, (W + max(d.textlength(r, font=f) for r in rows)) / 2 + 30, 140),
                        radius=16, fill=(0, 0, 0, 170))
    for k, r in enumerate(rows):
        d.text(((W - d.textlength(r, font=f)) / 2, 150 - h + 5 + k * 56), r, font=f, fill=(255, 255, 255))
    p = TMP / f"cap_{i:03d}.png"
    img.save(p)
    return p


def label_png(text, name):
    img = Image.new("RGBA", (W, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(28, True)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((40, 14, 40 + tw + 36, 62), radius=24, fill=(224, 122, 31, 235))
    d.text((58, 20), text, font=f, fill=(255, 255, 255))
    p = TMP / f"label_{name}.png"
    img.save(p)
    return p


slides = {
    "slide_title": slide("slide_title", [
        ("StepCards", 120, True, INK),
        ("One demonstration video → checked picture step cards", 54, False, INK),
        ("", 30, False, INK),
        ("Teachers make task-analysis cards by hand:", 44, False, MUTED),
        ("film · pause · screenshot · write · print", 44, False, MUTED),
        ("", 30, False, INK),
        ("Built during the Meta AI Developer Hackathon · Indie track · LogicCraft", 34, True, ACCENT),
    ]),
    "slide_close": slide("slide_close", [
        ("Measured in this build", 64, True, INK),
        (f"• {video_sec // 60} min {video_sec % 60} s first-person video → {len(cards)} cards in {make_min:.1f} min, about ${make_cost:.2f}", 42, False, INK),
        ("• Coach mode test replay: answers in about 3.6 s, about $0.08 per minute", 42, False, INK),
        ("• Only Meta models: Muse Spark · SAM 3.1 · Muse Voice Transcribe", 42, False, INK),
        ("", 24, False, INK),
        ("Next", 64, True, ACCENT),
        ("• Ray-Ban Meta glasses to film the demonstration and to coach", 42, False, INK),
        ("• Cards shared to WhatsApp / Messenger", 42, False, INK),
        ("• Open-weight Muse Spark inside schools: student video stays local", 42, False, INK),
    ]),
    "slide_credits": slide("slide_credits", [
        ("Credits", 64, True, INK),
        ("Sample video: \"POV Morning Latte in Costa Rica ASMR\" by Cornffy", 40, False, INK),
        ("YouTube vqv_DMMDqC8 · CC BY · Korean narration added with macOS synthetic voice", 36, False, MUTED),
        ("English narration: synthetic voice", 36, False, MUTED),
        ("", 24, False, INK),
        ("StepCards · LogicCraft · Meta AI Developer Hackathon 2026", 40, True, ACCENT),
    ]),
}

parts = []
for idx, (name, rec, text) in enumerate(SEGMENTS):
    # 내레이션
    if text:
        aiff = TMP / f"{name}.aiff"
        sh("say", "-v", "Samantha", "-r", "175", "-o", aiff, text)
        nar = duration(aiff)
    else:
        aiff, nar = None, 0
    seg_len = max(nar + 0.8, 4.0)
    if rec:  # 녹화를 너무 빨리 돌리면 화면을 못 읽는다: 장면마다 최대 배속을 두고, 모자라면 장면을 늘린다
        seg_len = max(seg_len, duration(OUT / rec) / MAX_SPEED[name])
    # 화면
    base = TMP / f"{name}_v.mp4"
    if name in slides:
        sh("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", slides[name], "-t", seg_len, "-r", 30, "-pix_fmt", "yuv420p", "-c:v", "libx264", base)
    elif name == "clip_input":
        sh("ffmpeg", "-v", "error", "-y", "-ss", 120, "-i", ROOT / "samples" / "pov_latte_narrated.mp4", "-t", seg_len, "-an",
           "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps=30", "-pix_fmt", "yuv420p", "-c:v", "libx264", base)
    else:
        src = OUT / rec
        speed = max(1.0, duration(src) / seg_len)  # 녹화가 길면 빨리 감기, 짧으면 마지막 화면 정지
        sh("ffmpeg", "-v", "error", "-y", "-i", src, "-an", "-vf",
           f"{CROP.get(name, '')}setpts=PTS/{speed},scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0xf6f4ef,"
           f"tpad=stop_mode=clone:stop_duration={seg_len},fps=30",
           "-t", seg_len, "-pix_fmt", "yuv420p", "-c:v", "libx264", base)
    # 자막(문장 단위, 글자 수 비율로 시간 배분) + 위쪽 표시
    overlays, inputs = [], []
    if text:
        sents = re.findall(r"[^.!?]+[.!?]", text)
        total = sum(len(s) for s in sents)
        t = 0.3
        for k, s in enumerate(sents):
            dt = nar * len(s) / total
            inputs.append(caption_png(s.strip(), idx * 100 + k))
            overlays.append((0, H - 170, t, t + dt))
            t += dt
    if name in LABELS:
        inputs.append(label_png(LABELS[name], name))
        overlays.append((0, 10, 0, seg_len))
    seg = TMP / f"{idx:02d}_{name}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for p in inputs:
        cmd += ["-i", p]
    if aiff:
        cmd += ["-i", aiff]
    else:
        cmd += ["-f", "lavfi", "-t", seg_len, "-i", "anullsrc=r=44100:cl=stereo"]
    chain, last = [], "[0:v]"
    for k, (x, y, a, b) in enumerate(overlays):
        chain.append(f"{last}[{k + 1}:v]overlay={x}:{y}:enable='between(t,{a:.2f},{b:.2f})'[o{k}]")
        last = f"[o{k}]"
    a_in = len(inputs) + 1
    chain.append(f"[{a_in}:a]adelay=300|300,apad,atrim=0:{seg_len},aformat=sample_rates=44100:channel_layouts=stereo[a]")
    cmd += ["-filter_complex", ";".join(chain), "-map", last if overlays else "0:v", "-map", "[a]",
            "-t", seg_len, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", seg]
    sh(*cmd)
    parts.append(seg)
    print(f"{name}: {seg_len:.1f}s")

lst = TMP / "list.txt"
lst.write_text("".join(f"file '{p}'\n" for p in parts))
final = OUT / "stepcards_demo.mp4"
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", final)
print(f"완성: {final} · {duration(final):.1f}s")
