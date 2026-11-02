# 데모 v3 합치기: record_v3.mjs 장면 + 영어 내레이션(합성 음성) + 자막 + 꼬리표 → demo/out/v3/stepcards_demo_v3.mp4
# 사용: .venv/bin/python demo/compose_v3.py <만들기 실행 id>
# 숫자는 기록에서만 뽑는다(만들기 = 이번 실행 progress.json, 따라 하기 = coach.marks.json, Glimmer = 6d5279d1379e)
import json, math, os, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
KO = os.environ.get("DEMO_LANG") == "ko"  # 한글판: DEMO_LANG=ko (녹화도 같은 변수로 한국어 화면)
V3 = ROOT / "demo" / "out" / ("v3ko" if KO else "v3")
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
LAG_MED = round(sorted(lags)[len(lags) // 2])
FOLLOW_X = max(2.0, round((last_turn - v_start + 6) / 32 * 2) / 2)  # 따라 하기 장면을 약 32초로(0.5 단위 배속, 화면 꼬리표에 그대로)

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
    ("follow", "duo_coach", (v_start, last_turn - v_start + 6, FOLLOW_X),
     f"Replay at {FOLLOW_X:g}× · the demonstration video plays as the camera · live Muse Spark decisions",
     "On the learner's side, the cards follow the hands. Here the same napkin video plays as the camera. "
     f"Muse Spark compares the camera with photos of each step from the demonstration. The cards turned on their own all the way to card {auto_to}, a median of {LAG_MED} seconds after each step ended. "
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
     "What we have not done yet: test with learners, and with a different person on a live camera."),
    ("close", "slide_close", None, None,
     "One video. Checked cards. Help only when needed. StepCards."),
]

if KO:  # 한글판 꼬리표·내레이션(숫자는 위와 같은 기록에서)
    k = re.search(r"문제 (\d+)개", splits[0]["msg"]).group(1) if len(splits) > 1 else ""
    note = f"이번 실행에서는 첫 답이 규칙 {k}개를 어겨 이유와 함께 돌려보냈고, {len(splits)}번째 답이 통과했어요. " if len(splits) > 1 else "이번 실행에서는 모든 카드가 처음에 검사를 통과했어요. "
    KO_TEXT = {
        "open": ("다시 재생 · 시범 영상을 카메라 대신 흘림 · Muse Spark 실제 판단",
                 "카드를 보세요. 손이 한 단계를 끝내고 몇 초 뒤, 다음 카드가 휴대폰과 안경에 함께 떠요."),
        "problem": (None, "StepCards는 특수교사와, 직업 훈련을 받는 지적장애 학생을 위한 도구예요. "
                    "지금은 교사가 단계 그림 카드를 손으로 만들어요. 찍고, 멈추고, 캡처하고, 쓰고, 인쇄하죠. StepCards는 시범 영상 하나로 이 카드를 만들어요."),
        "making": ("실제 실행 · Muse Voice Transcribe · Muse Spark · SAM 3.1 · 코드 검사기",
                   "교사는 레이밴 메타 안경이 보는 것처럼 눈높이에서 한 번 시범을 찍어 영상을 넣어요. "
                   "Muse Voice Transcribe가 말로 한 설명을 받아 적는데, 이 영상에는 말소리가 없어요. "
                   "Muse Spark가 영상을 동작 하나씩의 단계로 나누고, 쉬운 한국어와 영어 문장을 써요. "
                   "그다음 모델이 아니라 코드가 모든 카드를 검사하고, 걸리면 이유를 붙여 돌려보내요. " + note +
                   f"SAM 3.1은 손에 든 물건을 찾아요. {round(video_s / 60)}분짜리 영상이 {make_s:.0f}초 만에 카드 {n_cards}장이 됐고, 비용은 약 {make_cost * 100:.0f}센트였어요."),
        "edit": ("교사 확인 · 고칠 때마다 다시 검사",
                 "결정은 교사가 해요. 문장에 동작을 하나 더 넣으면 카드가 빨갛게 바뀌고, 빼면 통과해요. "
                 "카드마다 사진, 영상에서 뽑은 움직임, 시범을 따라 그린 3D 접기 중에서 고를 수 있어요."),
        "follow": (f"{FOLLOW_X:g}배속 다시 재생 · 시범 영상을 카메라 대신 흘림 · Muse Spark 실제 판단",
                   "학생 쪽에서는 카드가 손을 따라가요. 여기서도 같은 냅킨 영상을 카메라 대신 흘렸어요. Muse Spark가 카메라 화면을 시범 영상의 단계 사진과 맞춰 봐요. "
                   f"카드는 {auto_to}번까지 저절로 넘어갔고, 단계가 끝나고 중간값 {LAG_MED}초 뒤였어요. 안경 화면은 레이밴 디스플레이용으로 만들었어요."),
        "help": ("필요할 때만 도움 · 오른쪽은 교사 현황판",
                 "도움은 글만으로 시작해요. 학생이 막히면 한 칸씩 늘어나요. 그림, 문장 읽어 주기, 그다음 움직임이에요. "
                 "도움을 다 써도 안 되면 '도와줘요'가 교사 현황판에 떠요. 교사가 '갈게요'를 누르면 학생 화면에 도와주러 온다고 나와요. "
                 "칭찬도, 점수도, 저장하는 영상도 없어요."),
        "jobs": ("견본 카드 · 중증장애인 맞춤형 국가 일자리 직무 · CC BY 영상",
                 "기계가 판단하면 안 되는 일도 있어요. 사람을 차에 태우는 돌봄 일은 카메라를 켜지 않고, 끝났는지는 사람이 정해요. "
                 "중증장애인 맞춤형 국가 일자리 직무로 견본 카드를 만들었어요. 공개 라이선스 영상으로 만들었고, 한국 수어 인사도 있어요."),
        "glimmer": (f"이 맥에서 돌린 기록 · 공개 가중치 Muse Glimmer · {g_s}초 · $0",
                    f"영상을 밖으로 보낼 수 없는 학교에서는 같은 과정을 공개 가중치 모델 Muse Glimmer로 맥에서 돌려요. "
                    f"이 냅킨 영상이 {g_s}초 만에 검사를 통과한 카드 {g_cards}장이 됐고, API 비용은 0원이었어요. "
                    "아직 하지 못한 것도 있어요. 학생과 함께한 시험, 그리고 다른 사람이 실제 카메라로 따라 하는 시험이에요."),
        "close": (None, "영상 하나, 검사한 카드, 필요할 때만 도움. StepCards."),
    }
    SEGMENTS = [(n, lay, sp, *KO_TEXT[n]) for n, lay, sp, _, _ in SEGMENTS]


def slide_close():
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    models = "Muse Spark · SAM 3.1 · Muse Voice Transcribe · Muse Image · Muse Glimmer"
    rows = [("StepCards", 120, True, INK), ("영상 하나 → 검사한 카드 → 필요할 때만 도움" if KO else "One video → checked cards → help only when needed", 52, False, INK), ("", 40, False, INK),
            (("Meta 모델로 만듦: " if KO else "Built with Meta models: ") + models, 36, False, MUTED),
            ("Meta 제품 아님 · 로직크래프트 제작" if KO else "Not a Meta product · made by LogicCraft", 36, False, MUTED), ("", 30, False, INK),
            ("stepcards-production.up.railway.app", 44, True, ACCENT),
            ("견본 영상: CC BY, 앱과 README에 출처 표기 · 한국어 내레이션: 합성 음성" if KO else "Sample videos: CC BY, credited in the app and README · English narration: synthetic voice", 30, False, MUTED)]
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


T_GLASS = "레이밴 디스플레이 착용 시야 · 시뮬레이션" if KO else "Ray-Ban Display wearer's view · simulated"


def pill_png(text, name):
    """작은 꼬리표 한 개(글자 크기에 맞춘 그림)"""
    f = font(22, True)
    tw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=f))
    img = Image.new("RGBA", (tw + 28, 38), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, tw + 27, 37), radius=18, fill=(47, 99, 244, 235))
    d.text((14, 6), text, font=f, fill=(255, 255, 255))
    p = TMP / f"pill_{name}.png"
    img.save(p)
    return p


def sim_panel(gi, si, scene_t, trim, ln, sp, seg_len):
    """안경 착용 시야 580x440 → [panel]: 눈앞 장면(si 입력의 scene_t 초부터) + 안경테(si+1 입력) + 오른쪽 렌즈에 안경 화면(gi 입력)을 screen 합성.
    검은색 = 투명(Ray-Ban Display 는 빛을 더하는 화면, 오른쪽 렌즈에만). 두 영상 색 형식을 RGB 로 맞춰야 색이 안 틀어진다"""
    return (f"[{si}:v]trim=start={scene_t}:duration={ln},setpts=(PTS-STARTPTS)/{sp},crop=ih*4/3:ih,scale=580:440,fps=30,format=gbrp[sc];"
            f"{trim(gi)},scale=222:222[g];color=c=black:s=580x440:r=30:d={seg_len}[blk];[blk][g]overlay=316:88:shortest=1,format=gbrp[hud];"
            f"[sc][hud]blend=all_mode=screen:shortest=1,format=yuv420p[mix];[mix][{si + 1}:v]overlay=0:0[panel]")


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
        # 왼쪽 = 따라 하기 화면, 오른쪽 = 안경 착용 시야 시뮬레이션: 눈앞 장면(같은 시각의 카메라 영상) 위에 안경테,
        # 오른쪽 렌즈에 안경 화면을 screen 합성(검은색 = 투명, Ray-Ban Display 는 오른쪽 렌즈에만 화면). 화면에 '시뮬레이션'이라고 밝힌다
        fc = (f"{trim(1)},scale=1260:788[a];{sim_panel(2, 3, max(0, ss - v_start), trim, ln, sp, seg_len)};"
              f"[0][a]overlay=30:105[o1];[o1][panel]overlay=1320:230[o2];[o2][5:v]overlay=1320:186,tpad=stop_mode=clone:stop_duration={seg_len}")
        sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", bg, "-i", mp4("coach"), "-i", mp4("coach_glasses"), "-i", ROOT / "samples" / "napkin_butterfly.mp4",
           "-i", ROOT / "demo" / "glasses_frame.png", "-i", pill_png(T_GLASS, "glass"), "-filter_complex", fc, *enc)
    else:  # trio_help: 왼쪽 학습자, 오른쪽 위 안경 착용 시야(배경 = 7번 단계의 시범 장면), 오른쪽 아래 교사 현황판
        fc = (f"{trim(1)},scale=1152:720[a];{sim_panel(2, 4, 73, trim, ln, sp, seg_len)};[panel]scale=464:352[pb];{trim(3)},scale=680:435[c];"
              f"[0][a]overlay=30:110[o1];[o1][pb]overlay=1300:62[o2];[o2][c]overlay=1210:480[o3];[o3][6:v]overlay=1300:20,tpad=stop_mode=clone:stop_duration={seg_len}")
        sh("ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", bg, "-i", mp4("help"), "-i", mp4("help_glasses"), "-i", mp4("help_teacher"),
           "-i", ROOT / "samples" / "napkin_butterfly.mp4", "-i", ROOT / "demo" / "glasses_frame.png", "-i", pill_png(T_GLASS, "glass"), "-filter_complex", fc, *enc)
    return out


parts = []
for idx, (name, layout, span, label, text) in enumerate(SEGMENTS):
    aiff = TMP / f"{name}.aiff"
    sh("say", "-v", "Yuna" if KO else "Samantha", "-r", "200" if KO else "180", "-o", aiff, text)
    nar = duration(aiff)
    seg_len = round(max(nar + 0.9, (span[1] / span[2]) if span else 0), 2)
    base = base_video(name, layout, span, seg_len)
    sents = re.findall(r".+?[.!?](?=\s|$)", text)  # "SAM 3.1" 의 점에서 끊지 않게: 뒤에 빈칸이나 끝이 올 때만
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
final = V3 / ("stepcards_demo_v3_ko.mp4" if KO else "stepcards_demo_v3.mp4")
sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", final)
print(f"완성: {final} · {duration(final):.1f}s")
