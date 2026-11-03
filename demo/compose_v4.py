# 데모 v4 합치기(발표형·고화질): record_v3.mjs 장면(2배 해상도) + 내레이션(합성 음성) + 짧게 끊은 자막 → demo/out/v3[ko]/stepcards_demo_v4[_ko].mp4
# 사용: [DEMO_LANG=ko] .venv/bin/python demo/compose_v4.py <만들기 실행 id>
# 숫자는 기록에서만 뽑는다(만들기 = 이번 실행 progress.json, 따라 하기 = coach.marks.json, Glimmer = 6d5279d1379e)
# 연출: 그라데이션 배경, 둥근 창+그림자, 천천히 다가가는 줌, 장면 사이 디졸브, 상자 없는 굵은 자막
import json, os, re, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
KO = os.environ.get("DEMO_LANG") == "ko"
V3 = ROOT / "demo" / "out" / ("v3ko" if KO else "v3")
TMP = V3 / "tmp4"
TMP.mkdir(parents=True, exist_ok=True)
W, H, FPS, XF = 1920, 1080, 30, 0.35  # XF = 장면 사이 디졸브 길이
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
ENC = ["-r", FPS, "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "slow", "-crf", "16"]


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
    """프레임별 실제 시각 기록(frames.txt) → 30fps mp4. 마지막 그림이 ffconcat 규칙상 한 번 더 늘어나므로 기록된 합계로 자른다"""
    out = TMP / f"{name}.mp4"
    if not out.exists():
        ft = V3 / name / "frames.txt"
        total = sum(float(x.split()[1]) for x in ft.read_text().splitlines() if x.startswith("duration"))
        sh("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", 0, "-i", ft, "-t", f"{total:.3f}",
           "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "14", out)
    return out


# ---- 기록에서 뽑은 숫자 ----
def rdir(rid):
    """실행 폴더: runs/ 에 없으면 runs_trash/(11-03 목록 정리로 옮긴 데모용 실행)"""
    d = ROOT / "runs" / rid
    return d if d.exists() else ROOT / "runs_trash" / rid


MAKE = rdir(sys.argv[1])
prog = json.loads((MAKE / "progress.json").read_text())["events"]
make_s = round(prog[-1]["t"] - prog[0]["t"])
make_cost = round(sum(e.get("cost", 0) or 0 for e in prog) * 100)
video_min = round(int(re.search(r"영상 (\d+)초", next(e["msg"] for e in prog if e["stage"] == "extract")).group(1)) / 60)
n_cards = len(json.loads((MAKE / "cards.json").read_text())["cards"])
retried = len([e for e in prog if e["stage"] == "split"]) > 1
coach_m = marks("coach")
ends = {c["n"]: c["end"] for c in json.loads((rdir("d3d3d3d3d301") / "cards.json").read_text())["cards"]}
turns = [(t, int(re.search(r"card (\d+)", w).group(1)), float(re.search(r"at video ([\d.]+)s", w).group(1))) for t, w in coach_m if w.startswith("card ")]
lags = [vt - ends[n - 1] for _, n, vt in turns]
auto_to = max(n for _, n, _ in turns)
LAG = round(sorted(lags)[len(lags) // 2])
first_turn = min(turns, key=lambda x: abs(x[2] - ends[x[1] - 1]))[0]  # 첫 장면은 단계 끝과 가장 가깝게 넘어간 순간
v_start = at("coach", "video start")
last_turn = max(t for t, _, _ in turns)
FOLLOW_X = max(2.0, round((last_turn - v_start + 6) / 22 * 2) / 2)  # 따라 하기 장면 약 22초(설명 길이에 맞춤)
g = json.loads((ROOT / "runs" / "6d5279d1379e" / "progress.json").read_text())["events"]
g_s = round(g[-1]["t"] - g[0]["t"])
g_tries = len([e for e in g if e["stage"] == "split"])
g_cards = len(json.loads((ROOT / "runs" / "6d5279d1379e" / "cards.json").read_text())["cards"])
print(f"만들기 {make_s}s {make_cost}c {n_cards}장 재시도 {retried} / 자동 {auto_to}번까지 지연 중간 {LAG}s {[round(x, 1) for x in lags]} / Glimmer {g_s}s")

# ---- 대본: 말하듯 짧게. 금지: 'X가 아니라 Y', 셋씩 늘어놓기, 설명문 말투, 콜론 나열 ----
if not KO:
    ag = next(m for m in json.loads((V3 / "agent.marks.json").read_text())["marks"] if m["what"] == "agent")  # 에이전트 장면의 실제 결과
    ag_n, ag_cents, ag_wait = ag["changes"], round(ag["cost"] * 100), round(ag["wait_s"])
    retry_en = "One card broke a rule, so it went back for a rewrite and then passed. " if retried else ""
    S = [
        ("hook", "gen:hook", None, "Generated scene", "Some things you only learn by watching."),
        ("p_cafe", "gen:cafe", None, "First week at a cafe · generated scene", "New at the cafe? You watch the barista make it once, and then it's your turn."),
        ("p_reel", "gen:reel", None, "Learning from a Reel · generated scene", "Learning a dance from a Reel means pause, rewind, pause, rewind."),
        ("p_family", "gen:family", None, "Mom's recipe · generated scene", "Mom's recipe? It was never written down."),
        ("p_job", "gen:job", None, "Job training · generated scene", "Job coaches still make picture cards by hand, screenshot after screenshot, for every task."),
        ("p_sum", "statement", None, None, "Watching once isn't enough. Writing it all down takes hours."),
        ("reveal", "duo", (max(0, first_turn - 7), 12, 1), "Replay · demo video used as the camera · live decisions",
         "That's what StepCards is for. Film the task once, and the video becomes step cards, one action per card. While someone follows along, the app watches their hands through the camera and shows the next card when a step is done."),
        ("making", "single:making", None, "Real run · Muse Spark · SAM 3.1 · Voice Transcribe",
         f"Here's a real run: a {video_min}-minute napkin-folding video. Muse Spark splits it into steps, one action each, with timestamps and a short sentence in Korean and English. "
         f"Our code checks every card for overlapping timestamps, long sentences, or two actions in one card. {retry_en}"
         f"SAM 3.1 picks a photo for each card. {make_s} seconds later, we have {n_cards} cards, for about {make_cost} cents."),
        ("edit", "single:edit", None, "Review",
         "Next, the person who knows the task checks the cards. The rule checker reads each sentence. On card 2, I add \"pick up the napkin and\" at the start. Now it has two actions, so the card turns red and says why. Take it out and it passes. "
         "Yellow notes flag numbers that never came up in the video, and any left or right, since those are easy to mix up."),
        ("agent", "single:agent", None, f"Agent · Muse Spark runs our checker as a tool · {ag_wait} s wait cut",
         "Or just ask: \"simpler words for a learner who reads little.\" "
         f"Muse Spark rewrites {ag_n} cards and runs our checker on its draft before answering. "
         f"About {ag_cents} cents, with the {ag_wait}-second wait cut. Nothing changes until someone taps Apply."),
        ("follow", "duo", (v_start + 2, last_turn - v_start + 4, FOLLOW_X), f"Replay at {FOLLOW_X:g}x · demo video used as the camera",
         f"This is the learner's screen. The camera is on the left, the card on the right, and the glasses show the same card. "
         "The line under the camera says what the model sees, like \"still looks like before step 2,\" or \"step 2 looks like the demonstration, card 3.\" "
         f"In this replay the cards moved on by themselves up to card {auto_to}, about {LAG} seconds after each step."),
        ("help", "trio", (3.0, at("help", "learner sees help coming") + 2.0, 1), "Help when stuck · helper's board on the right",
         "Stuck? Help comes one step at a time. A picture, then the sentence read aloud, then a short clip. "
         "Still stuck? Tapping \"Ask for help\" puts the card number on the helper's board. They tap \"On my way,\" and the learner sees help is coming. There are no scores, and no video is kept."),
        ("breadth", "single:breadth", None, "Same app · CC BY demo videos",
         "Openly licensed videos also became cards for a cafe drink, a family stew, a cabinet, and a dance. "
         "We also made cards for jobs in Korea's national job program for people with severe disabilities. For care work, the camera stays off, and a person decides when each step is done."),
        ("glimmer", "single:glimmer", None, f"Recorded on this Mac · Muse Glimmer · {g_s} s · $0",
         f"Schools that can't send learners' video out can make the cards on one Mac with the open-weight Muse Glimmer model. "
         f"In this run, the checker sent the steps back {({1: 'once', 2: 'twice'}).get(g_tries - 1, f'{g_tries - 1} times')} before they passed. The napkin video became {g_cards} cards in {g_s} seconds, at no cost. "
         "We haven't yet tested it with real learners, or with a different person in front of a live camera."),
        ("close", "close", None, None, "Show it once. Then they've got it. StepCards."),
    ]
    GLASS, CLOSE = "Ray-Ban Display view · simulated", ["Show it once.", "Then they've got it."]
    CLOSE_SUB = ["Built with Meta models · Muse Spark · SAM 3.1 · Voice Transcribe · Muse Image · Muse Glimmer",
                 "Not a Meta product · made by LogicCraft", "Opening scenes are images generated on this Mac (Z-Image Turbo) · demo videos CC BY · voice by Google Chirp 3 HD"]
else:
    retry_ko = "규칙에 어긋난 카드가 하나 있어서 다시 쓰게 했고, 두 번째에 통과했어요. " if retried else ""
    S = [
        ("hook", "gen:hook", None, "생성한 장면", "보고 따라 해야만 배우는 일이 있죠."),
        ("p_cafe", "gen:cafe", None, "카페 첫 출근 · 생성한 장면", "카페 첫 출근 날, 바리스타가 한 번 보여 주면 바로 내 차례예요."),
        ("p_reel", "gen:reel", None, "릴스로 춤 배우기 · 생성한 장면", "릴스로 춤을 배우면 멈추고, 되감고, 또 멈춰요."),
        ("p_family", "gen:family", None, "엄마 레시피 · 생성한 장면", "엄마 레시피는 어디에도 적혀 있지 않고요."),
        ("p_job", "gen:job", None, "직업 훈련 · 생성한 장면", "직업 훈련 선생님은 그림 카드를 아직 손으로 만들어요. 일마다 화면을 캡처해서 하나씩 잘라요."),
        ("p_sum", "statement", None, None, "한 번 봐서는 모자라고, 다 적자니 몇 시간이 걸려요."),
        ("reveal", "duo", (max(0, first_turn - 7), 12, 1), "다시 재생 · 카메라 대신 시범 영상 · 판단은 실제 모델",
         "그래서 StepCards를 만들었어요. 일을 한 번 찍으면 그 영상이 단계 카드로 바뀌어요. 카드 한 장에 동작 하나예요. 따라 할 때는 카메라가 손을 보다가, 한 단계가 끝나면 다음 카드를 띄워요."),
        ("making", "single:making", None, "실제 실행 · Muse Spark · SAM 3.1 · Voice Transcribe",
         f"냅킨 접는 {video_min}분짜리 영상으로 실제로 돌려 볼게요. Muse Spark가 영상을 동작 하나씩 끊어서, 시간과 짧은 한국어·영어 문장을 붙여요. "
         f"저희 코드는 카드마다 시간이 겹치는지, 문장이 긴지, 동작이 둘인지 검사해요. {retry_ko}"
         f"SAM 3.1은 카드마다 사진을 골라요. {make_s}초 만에 카드 {n_cards}장이 나왔고, 비용은 {make_cost}센트쯤 들었어요."),
        ("edit", "single:edit", None, "확인하고 고치기",
         "이제 일을 아는 사람이 확인할 차례예요. 2번 카드에는 '오른쪽 윗모서리를 접으세요'라고 적혀 있어요. 앞에 '냅킨을 들고'를 붙이면 동작이 둘이 돼서, 카드가 빨갛게 바뀌고 이유를 알려 줘요. 지우면 통과해요. "
         "말한 적 없는 숫자나 뒤바뀌기 쉬운 왼쪽·오른쪽은 노란 메모로 표시해요. 카드마다 사진, 클립, 3D 접기 중에 골라요."),
        ("follow", "duo", (v_start + 2, last_turn - v_start + 4, FOLLOW_X), f"{FOLLOW_X:g}배속 다시 재생 · 카메라 대신 시범 영상",
         f"이건 따라 하는 사람의 화면이에요. 왼쪽이 카메라, 오른쪽이 카드이고, 안경에도 같은 카드가 떠요. "
         "카메라 아래 한 줄은 지금 본 것을 알려 줘요. '아직 2번 하기 전 모습이에요', '2번이 시범과 같아요, 3번 카드' 같은 식이에요. "
         f"이번 재생에서는 카드가 {auto_to}번까지 저절로 넘어갔어요. 단계를 마치고 {LAG}초쯤 지나서요."),
        ("help", "trio", (3.0, at("help", "learner sees help coming") + 2.0, 1), "막힐 때만 도움 · 오른쪽은 도와줄 사람 현황판",
         "막히면 도움이 한 칸씩 늘어요. 그림, 문장 읽어 주기, 짧은 영상 순서예요. "
         "그래도 안 되면 '도와줘요'를 눌러요. 그러면 도와줄 사람의 현황판에 카드 번호가 떠요. 그 사람이 '갈게요'를 누르면, 따라 하는 사람 화면에 도와주러 오고 있다고 나와요. 점수는 매기지 않고, 영상도 남기지 않아요."),
        ("breadth", "single:breadth", None, "같은 앱 · CC BY 시범 영상",
         "같은 방법으로 공개 영상에서 카페 음료, 집 찌개, 서랍장, 춤 카드도 만들었어요. "
         "중증장애인 맞춤형 국가 일자리의 직무 카드도 있어요. 돌봄 일에서는 카메라를 끄고, 단계를 마쳤는지는 사람이 정해요."),
        ("glimmer", "single:glimmer", None, f"이 맥에서 실행 · Muse Glimmer · {g_s}초 · 0원",
         f"학생 영상을 밖으로 보낼 수 없는 학교는 공개 모델 Muse Glimmer로 맥에서 전부 돌릴 수 있어요. "
         f"이번 기록에서는 검사기가 {g_tries - 1}번 돌려보낸 뒤에 통과했어요. 냅킨 영상이 {g_s}초 만에 카드 {g_cards}장이 됐고, 비용은 0원이에요. "
         "실제 학생과 해 보는 시험은 아직 못 했어요. 다른 사람이 실제 카메라로 따라 하는 시험도 아직이에요."),
        ("close", "close", None, None, "한 번 보여 주면, 따라 할 수 있어요. StepCards."),
    ]
    GLASS, CLOSE = "레이밴 디스플레이 착용 시야 · 시뮬레이션", ["한 번 보여 주면,", "따라 할 수 있어요."]
    CLOSE_SUB = ["Meta 모델로 만듦 · Muse Spark · SAM 3.1 · Voice Transcribe · Muse Image · Muse Glimmer",
                 "Meta 제품 아님 · 로직크래프트 제작", "앞 장면 그림은 이 맥에서 생성(Z-Image Turbo) · 시범 영상 CC BY · 목소리 Google Chirp 3 HD"]


# ---- 그림 재료 ----
def bg_png(light=False):
    p = TMP / ("bg_light.png" if light else "bg.png")
    if light and not p.exists():  # 어두운 앱 화면(따라 하기·도움) 장면: 같은 남색 위에 묻혀서(11-03 지적) 앱의 종이색 → 연한 흙색
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):
            k = y / H
            d.line((0, y, W, y), fill=(int(247 - 4 * k), int(246 - 16 * k), int(242 - 24 * k)))
        img.save(p)
    if not p.exists():
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img)
        for y in range(H):  # 위 짙은 남색 → 아래 남보라
            k = y / H
            d.line((0, y, W, y), fill=(int(9 + 18 * k), int(13 + 22 * k), int(38 + 42 * k)))
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        ImageDraw.Draw(glow).ellipse((-300, -400, 900, 500), fill=(47, 99, 244))
        img = Image.blend(img, Image.composite(glow, img, glow.convert("L").point(lambda v: 255 if v else 0)).filter(ImageFilter.GaussianBlur(220)), 0.35)
        img.save(p)
    return p


def mask_png(w, h, r=26):
    p = TMP / f"mask_{w}x{h}.png"
    if not p.exists():
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=r, fill=255)
        m.save(p)
    return p


def shadow_png(w, h, pad=70):
    p = TMP / f"shadow_{w}x{h}.png"
    if not p.exists():
        s = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        ImageDraw.Draw(s).rounded_rectangle((pad, pad + 18, pad + w, pad + h + 18), radius=30, fill=(0, 0, 0, 150))
        s.filter(ImageFilter.GaussianBlur(28)).save(p)
    return p


def pill_png(text, name):
    """반투명 유리 꼬리표"""
    f = font(26, True)
    tw = int(ImageDraw.Draw(Image.new("RGBA", (1, 1))).textlength(text, font=f))
    img = Image.new("RGBA", (tw + 40, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, tw + 39, 47), radius=24, fill=(10, 14, 40, 170), outline=(255, 255, 255, 70), width=2)  # 어두운 유리: 밝은 영상 위에서도 읽히게
    d.text((20, 8), text, font=f, fill=(255, 255, 255))
    p = TMP / f"pill_{name}.png"
    img.save(p)
    return p


def text_png(rows, name, size, sub=()):
    """큰 글자 화면(한 줄 정리·마무리): 배경 없이 글자만(투명), 가운데"""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f, fs = font(size, True), font(30)
    total = len(rows) * int(size * 1.3) + (len(sub) * 46 + 40 if sub else 0)
    y = (H - total) // 2
    for r in rows:
        d.text(((W - d.textlength(r, font=f)) / 2, y), r, font=f, fill=(255, 255, 255))
        y += int(size * 1.3)
    y += 40
    for r in sub:
        d.text(((W - d.textlength(r, font=fs)) / 2, y), r, font=fs, fill=(200, 208, 235))
        y += 46
    p = TMP / f"text_{name}.png"
    img.save(p)
    return p


def wrap(text, f, width):
    d, rows, row = ImageDraw.Draw(Image.new("RGB", (1, 1))), [], ""
    for w in text.split():
        if row and d.textlength(row + " " + w, font=f) > width:
            rows.append(row); row = w
        else:
            row = (row + " " + w).strip()
    return rows + [row]


BREAK = {"and", "with", "so", "but", "then", "or", "while", "when", "after", "for", "to", "in", "on", "by", "like", "where", "which", "because"}


def chunks(text):
    """자막은 짧게, 끊는 곳은 자연스럽게: 문장 → 쉼표 → 너무 길면(영어 9낱말, 한국어 24자) 가운데에 가까운
    접속사·전치사 앞(한국어는 띄어쓰기)에서 둘로. 'a 2-minute napkin / video' 처럼 명사구가 갈리지 않게"""
    def long(ws):
        return len(" ".join(ws)) > 24 if KO else len(ws) > 9

    def split(ws):
        if not long(ws):
            return [" ".join(ws)]
        mid = len(ws) / 2
        cand = [i for i in range(2, len(ws) - 1) if KO or ws[i].lower().strip(",.") in BREAK]
        i = min(cand, key=lambda k: abs(k - mid)) if cand else round(mid)
        return split(ws[:i]) + split(ws[i:])
    out = []
    for sent in re.findall(r".+?[.!?](?=\s|$)", text) or [text]:
        for part in re.split(r"(?<=,)\s+", sent.strip()):
            out += split(part.split())
    return out


def caption_png(text, i):
    """상자 없는 굵은 자막(테두리로 어디서나 읽히게)"""
    img = Image.new("RGBA", (W, 130), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(50, True)
    d.text(((W - d.textlength(text, font=f)) / 2, 30), text, font=f, fill=(255, 255, 255), stroke_width=5, stroke_fill=(8, 10, 28))
    p = TMP / f"cap_{i:03d}.png"
    img.save(p)
    return p


def sim_panel(gi, si, scene_t, trim, ln, sp, seg_len):
    """안경 착용 시야 580x440 → [panel]: 눈앞 장면 + 안경테 + 오른쪽 렌즈에 안경 화면(screen 합성, 검은색 = 투명)"""
    return (f"[{si}:v]trim=start={scene_t}:duration={ln},setpts=(PTS-STARTPTS)/{sp},crop=ih*4/3:ih,scale=580:440,fps=30,format=gbrp[sc];"
            f"{trim(gi)},scale=222:222:flags=lanczos[g];color=c=black:s=580x440:r=30:d={seg_len}[blk];[blk][g]overlay=316:88:shortest=1,format=gbrp[hud];"
            f"[sc][hud]blend=all_mode=screen:shortest=1,format=yuv420p[mix];[mix][{si + 1}:v]overlay=0:0[panel]")


CROP = {"edit": (0.11, 0.10, 0.70, 0.70), "making": (0.07, 0.07, 0.60, 0.60), "agent": (0.12, 0.06, 0.76, 0.76)}  # 고치기: 2번 카드 줄, 만들기: 진행 목록, 에이전트: 부탁 칸과 답
FOCUS = {}  # 움직이는 확대는 정수 반올림으로 떨려서 쓰지 않는다
CROP["glimmer"] = (0.06, 0.20, 0.62, 0.62)  # Glimmer: 노란 재시도 상자 둘레를 처음부터 확대


def framed(src, w, h, x, y, seg_len, mi, si, out, push=0.0, crop=None, focus=None):
    """앱 화면을 둥근 창+그림자로, 천천히 다가가는 줌(push). mi/si = 가림·그림자 입력 번호
    crop = (x, y, 너비, 높이) 비율: 화면의 핵심 부분만 잘라 키운다. focus = (fx, fy, 최대 배율): 그 점으로 다가간다"""
    cut = f"crop=iw*{crop[2]}:ih*{crop[3]}:iw*{crop[0]}:ih*{crop[1]}," if crop else ""
    if focus:
        fx, fy, zm = focus
        zz = f"1+{zm - 1}*min(1,on/({seg_len}*{FPS}*0.55))"
        z = f"zoompan=z='{zz}':x='max(0,min(iw-iw/zoom,iw*{fx}-iw/zoom/2))':y='max(0,min(ih-ih/zoom,ih*{fy}-ih/zoom/2))':d=1:s={w}x{h}:fps={FPS}"
    else:
        z = f"zoompan=z='1+{push}*on/({seg_len}*{FPS})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={FPS}"
    return (f"{src},{cut}scale={w * 2}:{h * 2}:flags=lanczos,{z},format=yuva420p[a{out}];[{mi}:v]format=gray,scale={w}:{h}[m{out}];[a{out}][m{out}]alphamerge[am{out}];"
            f"[BG{out}][{si}:v]overlay={x - 70}:{y - 70}[bs{out}];[bs{out}][am{out}]overlay={x}:{y}")


def base_video(name, layout, span, seg_len):
    out = TMP / f"{name}_v.mp4"
    bg = ["-loop", 1, "-t", seg_len, "-i", bg_png(light=layout in ("duo", "trio"))]
    enc = ["-t", seg_len, *ENC, out]
    if layout == "statement":
        sents = re.findall(r".+?[.!?](?=\s|$)", next(t for n, _, _, _, t in S if n == name))
        txt = text_png([r for x in sents for r in wrap(x.strip(), font(84, True), W - 300)], name, 84)  # 문장 중간에서 줄이 바뀌지 않게
        sh("ffmpeg", "-v", "error", "-y", *bg, "-loop", 1, "-t", seg_len, "-i", txt, "-filter_complex",
           "[1:v]format=rgba,fade=in:st=0.15:d=0.5:alpha=1[t];[0:v][t]overlay=0:0", *enc)
        return out
    if layout == "close":
        txt = text_png(CLOSE, name, 96, CLOSE_SUB + ["stepcards-production.up.railway.app"])
        sh("ffmpeg", "-v", "error", "-y", *bg, "-loop", 1, "-t", seg_len, "-i", txt, "-filter_complex",
           "[1:v]format=rgba,fade=in:st=0.1:d=0.6:alpha=1[t];[0:v][t]overlay=0:0", *enc)
        return out
    if layout.startswith("gen:") and not (ROOT / "demo" / "gen" / f"{layout[4:]}.mp4").exists():
        # 생성 영상이 없으면 생성 그림(Z-Image Turbo)에 카메라 움직임: 천천히 다가가며 옆으로 조금 흐른다
        # (11-02 Wan 2.2 1248x704 영상은 디코딩에서 스왑 37GB 로 강제 종료됐다)
        # zoompan 은 프레임마다 위치를 정수 픽셀로 반올림해서 천천히 움직이면 덜덜 떨렸다 → 소수점 영역을 직접 잘라 키운다(부드러운 움직임)
        src = Image.open(ROOT / "demo" / "gen" / f"{layout[4:]}.png").convert("RGB")
        sw, sh_ = src.size
        n = int(round(seg_len * FPS))
        ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                               *map(str, enc)], stdin=subprocess.PIPE)
        for k in range(n):
            e = k / max(1, n - 1)
            e = e * e * (3 - 2 * e)  # 처음과 끝을 부드럽게
            z = 1.05 + 0.12 * e
            cw, ch = sw / z, sh_ / z
            x0 = (sw - cw) * (0.25 + 0.5 * e)
            y0 = (sh_ - ch) * (0.45 + 0.1 * e)
            ff.stdin.write(src.transform((W, H), Image.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.BICUBIC).tobytes())
        ff.stdin.close(); ff.wait()
        return out
    if layout.startswith("gen:"):  # 문제 상황: 이 맥에서 생성한 2초 영상(Wan 2.2). 최대 2배까지 천천히 늘리고, 다가가는 줌, 모자라면 마지막 그림 유지
        src = ROOT / "demo" / "gen" / f"{layout[4:]}.mp4"
        slow = min(2.0, max(1.0, seg_len / duration(src)))
        z = f"zoompan=z='1+0.05*on/({seg_len}*{FPS})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"
        sh("ffmpeg", "-v", "error", "-y", "-i", src, "-an", "-vf",
           f"setpts=PTS*{slow:.3f},minterpolate=fps={FPS}:mi_mode=blend,scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W * 2}:{H * 2},{z},tpad=stop_mode=clone:stop_duration={seg_len}", *enc)
        return out
    if layout.startswith("clip:"):  # 문제 상황: 견본의 실제 시범 영상(CC BY), 천천히 다가가는 줌
        _, rid, t, *opt = layout.split(":")
        top = "crop=iw:ih*0.78:0:0," if "top" in opt else ""  # 원본에 박힌 자막(아래)을 잘라 낸다
        z = f"zoompan=z='1+0.06*on/({seg_len}*{FPS})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"
        sh("ffmpeg", "-v", "error", "-y", "-ss", t, "-i", ROOT / "runs" / rid / "video.mp4", "-an", "-vf",
           f"{top}scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W * 2}:{H * 2},fps={FPS},{z},tpad=stop_mode=clone:stop_duration={seg_len}", *enc)
        return out
    if layout.startswith("single:"):  # 앱 화면 하나: 둥근 창, 녹화가 길면 빨리 감기
        src = mp4(layout.split(":")[1])
        speed = max(1.0, duration(src) / seg_len)
        w, h, x, y = 1408, 880, 256, 70
        rec = layout.split(":")[1]
        fc = framed(f"[1:v]setpts=PTS/{speed},tpad=stop_mode=clone:stop_duration={seg_len},fps={FPS}", w, h, x, y, seg_len, 2, 3, 0,
                    crop=CROP.get(rec), focus=FOCUS.get(rec)).replace("[BG0]", "[0:v]")
        sh("ffmpeg", "-v", "error", "-y", *bg, "-i", src, "-loop", 1, "-t", seg_len, "-i", mask_png(w, h), "-loop", 1, "-t", seg_len, "-i", shadow_png(w, h),
           "-filter_complex", fc, *enc)
        return out
    ss, ln, sp = span
    trim = lambda i: f"[{i}:v]trim=start={ss}:duration={ln},setpts=(PTS-STARTPTS)/{sp},tpad=stop_mode=clone:stop_duration={seg_len}"
    napkin, gframe = ROOT / "samples" / "napkin_butterfly.mp4", ROOT / "demo" / "glasses_frame.png"
    if layout == "duo":  # 왼쪽 따라 하기 화면(둥근 창), 오른쪽 안경 착용 시야
        w, h, x, y = 1232, 770, 64, 150
        fc = (f"{sim_panel(2, 3, max(0, ss - v_start), trim, ln, sp, seg_len)};"
              + framed(trim(1), w, h, x, y, seg_len, 5, 6, 0).replace("[BG0]", "[0:v]") + "[o1];"
              f"[o1][panel]overlay=1336:260[o2];[o2][7:v]overlay=1336:200")
        sh("ffmpeg", "-v", "error", "-y", *bg, "-i", mp4("coach"), "-i", mp4("coach_glasses"), "-i", napkin, "-loop", 1, "-t", seg_len, "-i", gframe,
           "-loop", 1, "-t", seg_len, "-i", mask_png(w, h), "-loop", 1, "-t", seg_len, "-i", shadow_png(w, h), "-i", pill_png(GLASS, "glass"), "-filter_complex", fc, *enc)
    else:  # trio: 왼쪽 학습자(둥근 창), 오른쪽 위 안경 착용 시야(배경 = 7번 단계의 시범 장면), 오른쪽 아래 선생님 현황판(둥근 창)
        w, h, x, y = 1120, 700, 56, 150
        tw, th, tx, ty = 640, 202, 1236, 540  # 현황판 위쪽(지금 따라 하는 중 · 도와줘요 · 갈게요)만 잘라 크게
        fc = (f"{sim_panel(2, 4, 73, trim, ln, sp, seg_len)};[panel]scale=464:352[pb];"
              + framed(trim(1), w, h, x, y, seg_len, 6, 7, 0).replace("[BG0]", "[0:v]") + "[o1];"
              + framed(trim(3), tw, th, tx, ty, seg_len, 8, 9, 1, push=0.0, crop=(0, 0, 1, 0.5)).replace("[BG1]", "[o1]") + "[o2];"
              f"[o2][pb]overlay=1324:118[o3];[o3][10:v]overlay=1324:62")
        sh("ffmpeg", "-v", "error", "-y", *bg, "-i", mp4("help"), "-i", mp4("help_glasses"), "-i", mp4("help_teacher"), "-i", napkin, "-loop", 1, "-t", seg_len, "-i", gframe,
           "-loop", 1, "-t", seg_len, "-i", mask_png(w, h), "-loop", 1, "-t", seg_len, "-i", shadow_png(w, h),
           "-loop", 1, "-t", seg_len, "-i", mask_png(tw, th), "-loop", 1, "-t", seg_len, "-i", shadow_png(tw, th), "-i", pill_png(GLASS, "glass"), "-filter_complex", fc, *enc)
    return out


# ---- 목소리: 구글 Chirp3-HD(디지털 챔피언 때 고른 Zephyr). 키(~/.gtts_key)가 없으면 맥 기본 음성 ----
GKEY = Path("~/.gtts_key").expanduser()
CACHE = ROOT / "demo" / "out" / "tts_cache"  # 같은 문장은 한 번만 만든다(비용)
RATE = 1.12 if KO else 1.17  # 1.0 이면 두 판 모두 3분 7초: 3분 안으로. 영어판은 11-03 대본 고친 뒤 1.12 로 181초라 조금 더 빠르게


def voice(text):
    import base64, hashlib, urllib.request
    if not GKEY.exists():
        out = TMP / f"say_{hashlib.sha1(text.encode()).hexdigest()[:12]}.aiff"
        sh("say", "-v", "Yuna" if KO else "Samantha", "-r", "195" if KO else "178", "-o", out, text)
        return out
    lang, name = ("ko-KR", "ko-KR-Chirp3-HD-Zephyr") if KO else ("en-US", "en-US-Chirp3-HD-Zephyr")
    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / f"{hashlib.sha1((name + str(RATE) + text).encode()).hexdigest()[:16]}.mp3"
    if not out.exists():
        body = {"input": {"text": text}, "voice": {"languageCode": lang, "name": name}, "audioConfig": {"audioEncoding": "MP3", "speakingRate": RATE}}
        req = urllib.request.Request("https://texttospeech.googleapis.com/v1/text:synthesize?key=" + GKEY.read_text().strip(),
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        out.write_bytes(base64.b64decode(json.loads(urllib.request.urlopen(req, timeout=120).read())["audioContent"]))
    return out


# ---- 장면마다: 화면 + 말 + 자막 + 꼬리표 ----
parts, lens = [], []
for idx, (name, layout, span, label, text) in enumerate(S):
    aiff = voice(text)
    nar = duration(aiff)
    seg_len = round(max(nar + 0.9 + XF, (span[1] / span[2]) if span else 0), 2)
    base = base_video(name, layout, span, seg_len)
    inputs, overlays = [], []
    if layout not in ("statement", "close"):  # 큰 글자 화면은 글자가 곧 자막
        cs = chunks(text)
        total, t = sum(len(c) for c in cs), 0.3
        for k, c in enumerate(cs):
            dt = nar * len(c) / total
            inputs.append(caption_png(c, idx * 100 + k)); overlays.append((0, H - 150, t, t + dt)); t += dt
    if label:
        inputs.append(pill_png(label, name)); overlays.append((48 if layout.startswith("clip") else 64, 40, 0, seg_len))
    seg = TMP / f"{idx:02d}_{name}.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", base]
    for p in inputs:
        cmd += ["-i", p]
    cmd += ["-i", aiff]
    chain, last = [], "[0:v]"
    for k, (x, y, a, b) in enumerate(overlays):
        chain.append(f"{last}[{k + 1}:v]overlay={x}:{y}:enable='between(t,{a:.2f},{b:.2f})'[o{k}]"); last = f"[o{k}]"
    chain.append(f"[{len(inputs) + 1}:a]adelay=300|300,apad,atrim=0:{seg_len},aformat=sample_rates=48000:channel_layouts=stereo[a]")
    sh(*cmd, "-filter_complex", ";".join(chain), "-map", last if overlays else "0:v", "-map", "[a]", "-t", seg_len, *ENC, "-c:a", "aac", "-b:a", "192k", seg)
    parts.append(seg); lens.append(seg_len)
    print(f"{name}: {seg_len:.1f}s (말 {nar:.1f}s)")

# ---- 장면 사이 디졸브로 잇기 ----
cmd = ["ffmpeg", "-v", "error", "-y"]
for p in parts:
    cmd += ["-i", p]
vf, af, off, lv, la = [], [], 0.0, "[0:v]", "[0:a]"
for k in range(1, len(parts)):
    off += lens[k - 1] - XF
    vf.append(f"{lv}[{k}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[v{k}]"); lv = f"[v{k}]"
    af.append(f"{la}[{k}:a]acrossfade=d={XF}[a{k}]"); la = f"[a{k}]"
final = V3 / ("stepcards_demo_v4_ko.mp4" if KO else "stepcards_demo_v4.mp4")
sh(*cmd, "-filter_complex", ";".join(vf + af), "-map", lv, "-map", la, *ENC, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final)
print(f"완성: {final} · {duration(final):.1f}s")
