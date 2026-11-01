# 데모 v3 합치기: record_v3.mjs 장면 + 영어 내레이션(합성 음성) + 자막 + 꼬리표 → demo/out/v3/stepcards_demo_v3.mp4
# 사용: .venv/bin/python demo/compose_v3.py <만들기 실행 id>
# 숫자는 기록에서만 뽑는다(만들기 = 이번 실행 progress.json, 따라 하기 = coach.marks.json, Glimmer = 6d5279d1379e)
import json, math, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
V3 = ROOT / "demo" / "out" / "v3"
TMP = V3 / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
W, H = 1920, 1080
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
NAVY, INK, PAPER, ACCENT, CLAY, MUTED = (17, 24, 58), (17, 24, 58), (247, 246, 242), (47, 99, 244), (207, 131, 80), (95, 104, 136)


def font(size, bold=False):
    return ImageFont.truetype(FONT, size, index=6 if bold else 0)


def sh(*args):
    subprocess.run(list(map(str, args)), check=True)


def duration(path):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True, check=True).stdout)


def marks(scene):
    m = json.loads((V3 / f"{scene}.marks.json").read_text())["marks"]
    rec = next(x["t"] for x in m if x["what"] == "rec")
    return [(round(x["t"] - rec, 2), x["what"]) for x in m]


def at(scene, pattern):
    return next(t for t, w in marks(scene) if re.search(pattern, w))


def mp4(name):
    """screencast webm(길이 정보 없음, 화면이 안 바뀌면 프레임도 없음) → 30fps mp4"""
    out = TMP / f"{name}.mp4"
    if not out.exists():
        ft = V3 / name / "frames.txt"
        # 프레임별 실제 시각 기록이 있으면 그것으로. 마지막 그림은 ffconcat 규칙상 한 번 더 적혀 그 길이만큼 늘어나므로 기록된 합계로 자른다
        src = ["-f", "concat", "-safe", "0", "-i", ft, "-t", f"{sum(float(x.split()[1]) for x in ft.read_text().splitlines() if x.startswith('duration')):.3f}"] if ft.exists() else ["-i", V3 / f"{name}.webm"]
        sh("ffmpeg", "-v", "error", "-y", *src, "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out)
    return out


# ---- 기록에서 뽑은 숫자 ----
MAKE = ROOT / "runs" / sys.argv[1]
prog = json.loads((MAKE / "progress.json").read_text())["events"]
make_s = prog[-1]["t"] - prog[0]["t"]
make_cost = sum(e.get("cost", 0) or 0 for e in prog)
video_s = int(re.search(r"영상 (\d+)초", next(e["msg"] for e in prog if e["stage"] == "extract")).group(1))
n_cards = len(json.loads((MAKE / "cards.json").read_text())["cards"])
splits = [e for e in prog if e["stage"] == "split"]
if len(splits) > 1:
    RUN_NOTE = f"In this run, the first answer broke {re.search(r'문제 (\d+)개', splits[0]['msg']).group(1)} rules; the checker sent back the reasons, and try {len(splits)} passed. "
else:
    RUN_NOTE = "In this run, every card passed the checks on the first try. "
coach_m = marks("coach")
turned = [int(re.search(r"card (\d+)", w).group(1)) for _, w in coach_m if w.startswith("card ")]
auto_to = max(turned) if turned else 1
g = json.loads((ROOT / "runs" / "6d5279d1379e" / "progress.json").read_text())["events"]
g_s = round(g[-1]["t"] - g[0]["t"])
g_cards = len(json.loads((ROOT / "runs" / "6d5279d1379e" / "cards.json").read_text())["cards"])
print(f"만들기 {make_s:.0f}s ${make_cost:.2f} {n_cards}장 / 따라 하기 저절로 넘어간 카드 {turned} / Glimmer {g_s}s {g_cards}장")

# 콜드 오픈 = 저절로 넘어간 첫 순간 앞뒤 실제 속도 / 따라 하기 본편 = 영상 시작부터 마지막 자동 넘김 뒤까지 2배속
ends = {c["n"]: c["end"] for c in json.loads((ROOT / "runs" / "d3d3d3d3d301" / "cards.json").read_text())["cards"]}
# 콜드 오픈은 시범의 단계 끝(앞 카드의 end)과 가장 가깝게 넘어간 순간으로: 늦게 넘어간 순간을 쓰면 손이 이미 다음 동작 중이다
lags = [float(re.search(r"at video ([\d.]+)s", w).group(1)) - ends[int(re.search(r"card (\d+)", w).group(1)) - 1] for _, w in coach_m if w.startswith("card ")]
print("넘김 지연(앞 단계 끝 기준):", [round(x, 1) for x in lags])
first_turn = min(((t, abs(float(re.search(r"at video ([\d.]+)s", w).group(1)) - ends[int(re.search(r"card (\d+)", w).group(1)) - 1]))
                  for t, w in coach_m if w.startswith("card ")), key=lambda x: x[1])[0]
v_start = at("coach", "video start")
last_turn = max(t for t, w in coach_m if w.startswith("card "))

# (이름, 화면 배치, 원본 구간 [시작, 길이, 배속], 위쪽 꼬리표, 내레이션)
SEGMENTS = [
    ("open", "duo_coach", (max(0, first_turn - 7), 12, 1),
     "Replay · the demonstration video plays as the camera · live Muse Spark decisions",
     "Watch the card. A few seconds after the hands finish a step, StepCards shows the next one, on the phone and on the glasses."),
    ("problem", "home", (0, 15, 1), None,
     "StepCards is for special-education teachers and their learners with intellectual disabilities in job training. "
     "Today, teachers make step-by-step picture cards by hand: film, pause, screenshot, write, print. "
     "StepCards makes them from one demonstration video."),
    ("making", "single:making", None, "Real run · Muse Voice Transcribe · Muse Spark · SAM 3.1 · code checker",
     "The teacher films the task once at eye level, the way Ray-Ban Meta glasses see it, and drops in the video. "
     "Muse Voice Transcribe listens for spoken tips; this video has none. Muse Spark splits it into one-action steps, in plain Korean and English. "
     "Then code, not the model, checks every card, and sends failures back with the reason. " + RUN_NOTE +
     "SAM 3.1 finds the object in the hand. " f"A {round(video_s / 60)}-minute video became {n_cards} cards in {make_s:.0f} seconds, for about {make_cost * 100:.0f} cents."),
    ("edit", "single:edit", None, "Teacher review · every edit is checked again",
     "The teacher stays in charge. Add a second action to a sentence, and the card turns red. Take it out, and it passes. "
     "Each card can be a photo, a motion clip from the video, or a 3D fold drawn from the demonstration."),
    ("follow", "duo_coach", (v_start, last_turn - v_start + 6, 2.5),
     "Replay at 2.5× · the demonstration video plays as the camera · live Muse Spark decisions",
     "On the learner's side, the cards follow the hands. Here the same napkin video plays as the camera. "
     f"Muse Spark decides which step the hands are on. The cards turned on their own up to card {auto_to}, {math.floor(min(lags))} to {math.ceil(max(lags))} seconds after each step was done. "
     "The glasses view is built for Ray-Ban Display."),
    ("help", "trio_help", (1.5, at("help", "learner sees help coming") + 3.5, 1), "Help only when needed · the teacher's board on the right",
     "Help starts as text only. When the learner is stuck, it grows one step at a time: a picture, the sentence read aloud, then a motion clip. "
     "When the help runs out, Ask for help reaches the teacher's board. On my way, and the learner sees that help is coming. "
     "No praise, no scores, no video stored."),
    ("jobs", "single:jobs", None, "Sample cards · Korea's national jobs for people with severe disabilities · CC BY videos",
     "Some work should not be judged by a machine. For care work, like helping someone into a car, the camera stays off, and a person decides when it's done. "
     "We made sample cards for Korea's national jobs for people with severe disabilities, from openly licensed videos, including Korean Sign Language."),
    ("glimmer", "single:glimmer", None, f"Recorded run on this Mac · open-weight Muse Glimmer · {g_s} s · $0",
     f"For schools that can't send video out, the same pipeline runs on open-weight Muse Glimmer on a Mac. "
     f"This napkin video became {g_cards} checked cards in {g_s} seconds, at no API cost. "
     "What doesn't work yet: in our napkin test, the later steps that unfold hidden layers were not recognized, so the learner taps Next. "
     "And we have not yet tested with learners."),
    ("close", "slide_close", None, None,
     "One video. Checked cards. Help only when needed. StepCards."),
]


def slide_close():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    rows = [("StepCards", 120, True, INK), ("One video → checked cards → help only when needed", 52, False, INK), ("", 40, False, INK),
            ("Built with Meta models: Muse Spark · SAM 3.1 · Muse Voice Transcribe · Muse Image · Muse Glimmer", 36, False, MUTED),
            ("Not a Meta product · made by LogicCraft", 36, False, MUTED), ("", 30, False, INK),
            ("stepcards-production.up.railway.app", 44, True, ACCENT),
            ("Sample videos: CC BY, credited in the app and README · English narration: synthetic voice", 30, False, MUTED)]
    y = 250
    for t, s, b, c in rows:
        d.text((160, y), t, font=font(s, b), fill=c)
        y += int(s * 1.6)
    p = TMP / "slide_close.png"
    img.save(p)
    return p


def caption_png(text, i):
    img = Image.new("RGBA", (W, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(40)
    rows, row = [], ""
    for w in text.split():
        if d.textlength(row + " " + w, font=f) > W - 360 and row:
            rows.append(row); row = w
        else:
            row = (row + " " + w).strip()
    rows.append(row)
    rows = rows[-2:]
    h = 58 * len(rows) + 30
    wmax = max(d.textlength(r, font=f) for r in rows)
    d.rounded_rectangle(((W - wmax) / 2 - 30, 150 - h - 10, (W + wmax) / 2 + 30, 150), radius=16, fill=(0, 0, 0, 185))
    for k, r in enumerate(rows):
        d.text(((W - d.textlength(r, font=f)) / 2, 150 - h + 5 + k * 58), r, font=f, fill=(255, 255, 255))
    p = TMP / f"cap_{i:03d}.png"
    img.save(p)
    return p


def label_png(text, name):
    img = Image.new("RGBA", (W, 70), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(28, True)
    tw = d.textlength(text, font=f)
    d.rounded_rectangle((40, 14, 40 + tw + 36, 62), radius=24, fill=CLAY + (240,))
    d.text((58, 20), text, font=f, fill=(255, 255, 255))
    p = TMP / f"label_{name}.png"
    img.save(p)
    return p


def base_video(name, layout, span, seg_len):
    out = TMP / f"{name}_v.mp4"
    enc = ["-t", seg_len, "-r", 30, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "18", out]
    bg = f"color=c=0x11183a:s={W}x{H}:r=30:d={seg_len}"
    if layout == "slide_close":
        sh("ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", slide_close(), *enc)
        return out
    if layout.startswith("single:"):
        src = mp4(layout.split(":")[1])
        speed = max(1.0, duration(src) / seg_len)  # 녹화가 길면 빨리 감기, 짧으면 마지막 화면 정지
        sh("ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
           f"setpts=PTS/{speed},scale={W}:840:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:75:color=0x11183a,"  # 꼬리표 아래·자막 띠 위
           f"tpad=stop_mode=clone:stop_duration={seg_len},fps=30", *enc)
        return out
    if layout == "home":
        src = mp4("home")
        sh("ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
           f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,tpad=stop_mode=clone:stop_duration={seg_len},fps=30", *enc)
        return out
    ss, ln, sp = span
    trim = lambda i: f"[{i}:v]trim=start={ss}:duration={ln},setpts=(PTS-STARTPTS)/{sp}"
    if layout == "duo_coach":  # 왼쪽 휴대폰 화면, 오른쪽 안경 화면
        # 왼쪽 위 = 카메라 자리에 흘린 시범 영상(크게: 손이 단계를 끝내는 것이 보여야 한다), 왼쪽 아래 = 안경, 오른쪽 = 휴대폰 화면
        vs = ss - v_start  # 녹화 시각 → 시범 영상 시각
        cam = f"[3:v]trim=start={max(0, vs)}:duration={ln},setpts=(PTS-STARTPTS)/{sp},scale=720:405"
        fc = (f"{trim(1)},scale=1140:713[a];{trim(2)},scale=360:360[b];{cam}[c];"
              f"[0][c]overlay=30:95[o1];[o1][b]overlay=210:520[o2];[o2][a]overlay=765:130,tpad=stop_mode=clone:stop_duration={seg_len}")
        sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", bg, "-i", mp4("coach"), "-i", mp4("coach_glasses"), "-i", ROOT / "samples" / "napkin_butterfly.mp4", "-filter_complex", fc, *enc)
    else:  # trio_help: 왼쪽 학습자, 오른쪽 위 안경, 오른쪽 아래 교사 현황판
        fc = (f"{trim(1)},scale=1152:720[a];{trim(2)},scale=400:400[b];{trim(3)},scale=680:435[c];"
              f"[0][a]overlay=30:110[o1];[o1][b]overlay=1370:60[o2];[o2][c]overlay=1210:480,tpad=stop_mode=clone:stop_duration={seg_len}")
        sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", bg, "-i", mp4("help"), "-i", mp4("help_glasses"), "-i", mp4("help_teacher"), "-filter_complex", fc, *enc)
    return out


parts = []
for idx, (name, layout, span, label, text) in enumerate(SEGMENTS):
    aiff = TMP / f"{name}.aiff"
    sh("say", "-v", "Samantha", "-r", "180", "-o", aiff, text)
    nar = duration(aiff)
    seg_len = round(max(nar + 0.9, (span[1] / span[2]) if span else 0), 2)
    base = base_video(name, layout, span, seg_len)
    sents = re.findall(r"[^.!?]+[.!?]", text)
    total, t = sum(len(s) for s in sents), 0.3
    inputs, overlays = [], []
    for k, s in enumerate(sents):
        dt = nar * len(s) / total
        inputs.append(caption_png(s.strip(), idx * 100 + k)); overlays.append((0, H - 175, t, t + dt)); t += dt
    if label:
        inputs.append(label_png(label, name)); overlays.append((0, 20, 0, seg_len))
    seg = TMP / f"{idx:02d}_{name}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-i", aiff]
    chain, last = [], "[0:v]"
    for k, (x, y, a, b) in enumerate(overlays):
        chain.append(f"{last}[{k + 1}:v]overlay={x}:{y}:enable='between(t,{a:.2f},{b:.2f})'[o{k}]"); last = f"[o{k}]"
    chain.append(f"[{len(inputs) + 1}:a]adelay=300|300,apad,atrim=0:{seg_len},aformat=sample_rates=44100:channel_layouts=stereo[a]")
    sh(*cmd, "-filter_complex", ";".join(chain), "-map", last, "-map", "[a]", "-t", seg_len, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", seg)
    parts.append(seg)
    print(f"{name}: {seg_len:.1f}s (말 {nar:.1f}s)")

lst = TMP / "list.txt"
lst.write_text("".join(f"file '{p}'\n" for p in parts))
final = V3 / "stepcards_demo_v3.mp4"
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", final)
print(f"완성: {final} · {duration(final):.1f}s")
