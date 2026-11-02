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
MAKE = ROOT / "runs" / sys.argv[1]
prog = json.loads((MAKE / "progress.json").read_text())["events"]
make_s = round(prog[-1]["t"] - prog[0]["t"])
make_cost = round(sum(e.get("cost", 0) or 0 for e in prog) * 100)
video_min = round(int(re.search(r"영상 (\d+)초", next(e["msg"] for e in prog if e["stage"] == "extract")).group(1)) / 60)
n_cards = len(json.loads((MAKE / "cards.json").read_text())["cards"])
retried = len([e for e in prog if e["stage"] == "split"]) > 1
coach_m = marks("coach")
ends = {c["n"]: c["end"] for c in json.loads((ROOT / "runs" / "d3d3d3d3d301" / "cards.json").read_text())["cards"]}
turns = [(t, int(re.search(r"card (\d+)", w).group(1)), float(re.search(r"at video ([\d.]+)s", w).group(1))) for t, w in coach_m if w.startswith("card ")]
lags = [vt - ends[n - 1] for _, n, vt in turns]
auto_to = max(n for _, n, _ in turns)
LAG = round(sorted(lags)[len(lags) // 2])
first_turn = min(turns, key=lambda x: abs(x[2] - ends[x[1] - 1]))[0]  # 첫 장면은 단계 끝과 가장 가깝게 넘어간 순간
v_start = at("coach", "video start")
last_turn = max(t for t, _, _ in turns)
FOLLOW_X = max(2.0, round((last_turn - v_start + 6) / 20 * 2) / 2)
g = json.loads((ROOT / "runs" / "6d5279d1379e" / "progress.json").read_text())["events"]
g_s = round(g[-1]["t"] - g[0]["t"])
print(f"만들기 {make_s}s {make_cost}c {n_cards}장 재시도 {retried} / 자동 {auto_to}번까지 지연 중간 {LAG}s {[round(x, 1) for x in lags]} / Glimmer {g_s}s")

# ---- 대본: 말하듯 짧게. 금지: 'X가 아니라 Y', 셋씩 늘어놓기, 설명문 말투, 콜론 나열 ----
if not KO:
    retry_en = "One card broke a rule, so it went back and came out right. " if retried else ""
    S = [
        ("hook", "gen:hook", None, "Generated scene", "Some things you only learn by watching."),
        ("p_cafe", "gen:cafe", None, "First week at a cafe · generated scene", "New at the cafe? You watch the barista once, and then it's your turn."),
        ("p_reel", "gen:reel", None, "Learning from a Reel · generated scene", "Learning a dance from a Reel means pause, rewind, pause, rewind."),
        ("p_family", "gen:family", None, "Mom's recipe · generated scene", "Mom's recipe? It was never written down."),
        ("p_job", "gen:job", None, "Job training · generated scene", "Job coaches still make picture cards by hand, screenshot after screenshot, for every task."),
        ("p_sum", "statement", None, None, "Watching once isn't enough. Writing it all down takes hours."),
        ("reveal", "duo", (max(0, first_turn - 7), 12, 1), "Replay · demo video used as the camera · live decisions",
         "StepCards turns one video into step cards. Then the camera watches your hands, and a few seconds after you finish a step, the next card shows up on your phone or your glasses."),
        ("making", "single:making", None, "Real run · Muse Spark · SAM 3.1 · Voice Transcribe",
         f"Here's a real run. Drop in a {video_min}-minute napkin video. Muse Spark breaks it into small steps and writes each one in plain Korean and English. "
         f"Our code checks every card and sends anything that breaks a rule back to the model. {retry_en}"
         f"{make_s} seconds later, {n_cards} cards, for about {make_cost} cents."),
        ("edit", "single:edit", None, "Review",
         "You stay in control. Put two actions in one card and it turns red. Fix it and it passes. "
         "Numbers nobody said out loud, and anything about left or right, get a yellow note so you double-check. "
         "Each card can be a photo, a clip from the video, or a 3D fold."),
        ("follow", "duo", (v_start, last_turn - v_start + 6, FOLLOW_X), f"Replay at {FOLLOW_X:g}x · demo video used as the camera",
         f"Now the learner's side. Muse Spark matches the camera to the demo, one step at a time. In this replay the cards moved on by themselves up to card {auto_to}, about {LAG} seconds after each step."),
        ("help", "trio", (1.5, at("help", "learner sees help coming") + 3.5, 1), "Help when stuck · teacher's board on the right",
         "Stuck? Help comes in small steps. First a picture, then the sentence read aloud, then a short clip. "
         "Still stuck, one tap pings the teacher. They tap On my way, and the learner sees help is coming. No scores, and no video is kept."),
        ("breadth", "single:breadth", None, "Same app · CC BY demo videos",
         "Same app, very different jobs. A cafe drink, a family stew, a cabinet, a dance. "
         "And Korea's national jobs for people with severe disabilities, like helping someone into a car, where the camera stays off and a person says when it's done."),
        ("glimmer", "single:glimmer", None, f"Recorded on this Mac · Muse Glimmer · {g_s} s · $0",
         f"Schools that can't send video anywhere can run it on a Mac with the open Muse Glimmer model. This napkin video took {g_s} seconds and cost nothing. "
         "What we haven't done yet is test it with real learners, and with someone else on a live camera."),
        ("close", "close", None, None, "Show it once. Then they've got it. StepCards."),
    ]
    GLASS, CLOSE = "Ray-Ban Display view · simulated", ["Show it once.", "Then they've got it."]
    CLOSE_SUB = ["Built with Meta models · Muse Spark · SAM 3.1 · Voice Transcribe · Muse Image · Muse Glimmer",
                 "Not a Meta product · made by LogicCraft", "Opening scenes are images generated on this Mac (Z-Image Turbo) · demo videos CC BY · synthetic voice"]
else:
    retry_ko = "규칙에 어긋난 카드가 하나 있어서 다시 쓰게 했고, 두 번째에 통과했어요. " if retried else ""
    S = [
        ("hook", "gen:hook", None, "생성한 장면", "보고 따라 해야만 배우는 일이 있죠."),
        ("p_cafe", "gen:cafe", None, "카페 첫 출근 · 생성한 장면", "카페 첫 출근 날, 바리스타가 한 번 보여 주면 바로 내 차례예요."),
        ("p_reel", "gen:reel", None, "릴스로 춤 배우기 · 생성한 장면", "릴스로 춤을 배우면 멈추고, 되감고, 또 멈춰요."),
        ("p_family", "gen:family", None, "엄마 레시피 · 생성한 장면", "엄마 레시피는 어디에도 적혀 있지 않고요."),
        ("p_job", "gen:job", None, "직업 훈련 · 생성한 장면", "직업 훈련 선생님은 아직도 그림 카드를 손으로 만들어요. 일마다 캡처하고 자르면서요."),
        ("p_sum", "statement", None, None, "한 번 봐서는 모자라고, 다 적자니 몇 시간이 걸려요."),
        ("reveal", "duo", (max(0, first_turn - 7), 12, 1), "다시 재생 · 시범 영상을 카메라 대신 · 실제 판단",
         "StepCards는 영상 하나로 단계 카드를 만들어요. 따라 할 때는 카메라가 손을 보고, 한 단계를 마치면 몇 초 뒤 다음 카드를 휴대폰이나 안경에 띄워요."),
        ("making", "single:making", None, "실제 실행 · Muse Spark · SAM 3.1 · Voice Transcribe",
         f"실제로 돌려 볼게요. {video_min}분짜리 냅킨 영상을 넣으면 Muse Spark가 작은 단계로 나누고, 쉬운 한국어와 영어로 문장을 써요. "
         f"카드는 우리 코드가 하나하나 검사해서, 규칙에 어긋나면 다시 쓰게 해요. {retry_ko}{make_s}초 뒤 카드 {n_cards}장, 비용은 {make_cost}센트쯤이에요."),
        ("edit", "single:edit", None, "확인하고 고치기",
         "고치는 건 일을 아는 사람 몫이에요. 카드 하나에 동작을 두 개 넣으면 빨갛게 바뀌고, 고치면 통과해요. "
         "말한 적 없는 숫자나 왼쪽·오른쪽은 노란 메모로 한 번 더 보게 해요. 카드마다 사진, 영상 클립, 3D 접기 중에 골라요."),
        ("follow", "duo", (v_start, last_turn - v_start + 6, FOLLOW_X), f"{FOLLOW_X:g}배속 다시 재생 · 시범 영상을 카메라 대신",
         f"이제 따라 하는 쪽이에요. Muse Spark가 카메라 화면을 시범 장면과 한 단계씩 맞춰 봐요. 이 재생에서는 {auto_to}번 카드까지 저절로 넘어갔고, 단계를 마치고 {LAG}초쯤 뒤였어요."),
        ("help", "trio", (1.5, at("help", "learner sees help coming") + 3.5, 1), "막힐 때만 도움 · 오른쪽은 선생님 현황판",
         "막히면 도움이 조금씩 늘어요. 그림, 문장 읽어 주기, 짧은 영상 순서예요. "
         "그래도 안 되면 한 번 눌러 선생님께 알리고, 선생님이 갈게요를 누르면 학생 화면에 바로 떠요. 점수는 없고, 영상도 남기지 않아요."),
        ("breadth", "single:breadth", None, "같은 앱 · CC BY 시범 영상",
         "같은 앱으로 전혀 다른 일도 만들었어요. 카페 음료, 집 찌개, 서랍장 조립, 춤까지요. "
         "중증장애인 맞춤형 국가 일자리 직무도 있어요. 차에 타는 걸 돕는 일은 카메라를 끄고, 끝났는지는 사람이 정해요."),
        ("glimmer", "single:glimmer", None, f"이 맥에서 · Muse Glimmer · {g_s}초 · 0원",
         f"영상을 밖으로 보낼 수 없는 학교는 공개 모델 Muse Glimmer로 맥에서 돌리면 돼요. 이 냅킨 영상은 {g_s}초 걸렸고 비용은 0원이었어요. "
         "아직 못 한 것도 있어요. 실제 학생과의 시험, 그리고 다른 사람이 실제 카메라로 따라 하는 시험이에요."),
        ("close", "close", None, None, "한 번 보여 주면, 따라 할 수 있게. StepCards."),
    ]
    GLASS, CLOSE = "레이밴 디스플레이 착용 시야 · 시뮬레이션", ["한 번 보여 주면,", "따라 할 수 있게."]
    CLOSE_SUB = ["Meta 모델로 만듦 · Muse Spark · SAM 3.1 · Voice Transcribe · Muse Image · Muse Glimmer",
                 "Meta 제품 아님 · 로직크래프트 제작", "앞 장면은 이 맥에서 생성한 그림(Z-Image Turbo) · 시범 영상 CC BY · 합성 음성"]


# ---- 그림 재료 ----
def bg_png():
    p = TMP / "bg.png"
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


def chunks(text):
    """자막은 짧게: 문장 → 쉼표 → 길이(영어 8낱말, 한국어 22자) 순으로 끊는다"""
    out = []
    for sent in re.findall(r".+?[.!?](?=\s|$)", text) or [text]:
        for part in re.split(r"(?<=,)\s+", sent.strip()):
            words, cur = part.split(), []
            for w in words:
                cur.append(w)
                if (not KO and len(cur) >= 8) or (KO and len(" ".join(cur)) >= 22):
                    out.append(" ".join(cur)); cur = []
            if cur:
                out.append(" ".join(cur))
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


def framed(src, w, h, x, y, seg_len, mi, si, out, push=0.03):
    """앱 화면을 둥근 창+그림자로, 천천히 다가가는 줌(push). mi/si = 가림·그림자 입력 번호"""
    z = f"zoompan=z='1+{push}*on/({seg_len}*{FPS})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps={FPS}"
    return (f"{src},scale={w * 2}:{h * 2}:flags=lanczos,{z},format=yuva420p[a{out}];[{mi}:v]format=gray,scale={w}:{h}[m{out}];[a{out}][m{out}]alphamerge[am{out}];"
            f"[BG{out}][{si}:v]overlay={x - 70}:{y - 70}[bs{out}];[bs{out}][am{out}]overlay={x}:{y}")


def base_video(name, layout, span, seg_len):
    out = TMP / f"{name}_v.mp4"
    bg = ["-loop", 1, "-t", seg_len, "-i", bg_png()]
    enc = ["-t", seg_len, *ENC, out]
    if layout == "statement":
        txt = text_png(wrap(next(t for n, _, _, _, t in S if n == name), font(84, True), W - 300), name, 84)
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
        src = ROOT / "demo" / "gen" / f"{layout[4:]}.png"
        n = int(seg_len * FPS)
        z = f"zoompan=z='1.04+0.08*on/{n}':x='(iw-iw/zoom)*(0.35+0.3*on/{n})':y='(ih-ih/zoom)/2':d={n}:s={W}x{H}:fps={FPS}"
        sh("ffmpeg", "-v", "error", "-y", "-i", src, "-vf", f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W * 2}:{H * 2},{z}", *enc)
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
        fc = framed(f"[1:v]setpts=PTS/{speed},tpad=stop_mode=clone:stop_duration={seg_len},fps={FPS}", w, h, x, y, seg_len, 2, 3, 0).replace("[BG0]", "[0:v]")
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
        tw, th, tx, ty = 640, 410, 1236, 530
        fc = (f"{sim_panel(2, 4, 73, trim, ln, sp, seg_len)};[panel]scale=464:352[pb];"
              + framed(trim(1), w, h, x, y, seg_len, 6, 7, 0).replace("[BG0]", "[0:v]") + "[o1];"
              + framed(trim(3), tw, th, tx, ty, seg_len, 8, 9, 1, push=0.0).replace("[BG1]", "[o1]") + "[o2];"
              f"[o2][pb]overlay=1324:118[o3];[o3][10:v]overlay=1324:62")
        sh("ffmpeg", "-v", "error", "-y", *bg, "-i", mp4("help"), "-i", mp4("help_glasses"), "-i", mp4("help_teacher"), "-i", napkin, "-loop", 1, "-t", seg_len, "-i", gframe,
           "-loop", 1, "-t", seg_len, "-i", mask_png(w, h), "-loop", 1, "-t", seg_len, "-i", shadow_png(w, h),
           "-loop", 1, "-t", seg_len, "-i", mask_png(tw, th), "-loop", 1, "-t", seg_len, "-i", shadow_png(tw, th), "-i", pill_png(GLASS, "glass"), "-filter_complex", fc, *enc)
    return out


# ---- 장면마다: 화면 + 말 + 자막 + 꼬리표 ----
parts, lens = [], []
for idx, (name, layout, span, label, text) in enumerate(S):
    aiff = TMP / f"{name}.aiff"
    sh("say", "-v", "Yuna" if KO else "Samantha", "-r", "195" if KO else "178", "-o", aiff, text)
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
