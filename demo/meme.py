# 유머판 도입 밈 장면 3개(형식만 빌리고 그림은 이 맥 Z-Image Turbo 생성 · 글자는 직접): demo/gen/meme/*.png → demo/gen/meme/{owl,reel,screw}.mp4
# owl = '나머지 부엉이 그리기' 형식(1단계 · 2단계 = 완성품 · 내 결과), reel = 되감기 카운터, screw = 남은 나사
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

G = Path(__file__).resolve().parent / "gen" / "meme"
W, H, FPS = 1920, 1080, 30
FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
font = lambda s, b=True: ImageFont.truetype(FONT, s, index=6 if b else 0)


def cover(im, w, h, z=1.0, fx=0.5, fy=0.5):
    s = max(w / im.width, h / im.height) * z
    im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    x, y = int((im.width - w) * fx), int((im.height - h) * fy)
    return im.crop((x, y, x + w, y + h))


def bg():
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H; d.line((0, y, W, y), fill=(int(9 + 18 * k), int(13 + 22 * k), int(38 + 42 * k)))
    return img


def write(name, frames_fn, secs):
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-pix_fmt", "yuv420p", "-c:v", "libx264", "-crf", "16", str(G / f"{name}.mp4")], stdin=subprocess.PIPE)
    for k in range(int(secs * FPS)):
        ff.stdin.write(frames_fn(k / FPS).tobytes())
    ff.stdin.close(); ff.wait()


def ease(t): t = max(0.0, min(1.0, t)); return t * t * (3 - 2 * t)


def owl():
    base = bg()
    P = 520
    panels = [("Step 1", "Fold the napkin in half", "half"), ("Step 2", "Fold the rest of the swan", "swan"), ("Mine", "", "crumple")]
    pics = [cover(Image.open(G / f"{n}.png").convert("RGB"), P, P) for _, _, n in panels]
    xs = [120, 700, 1280]; appear = [0.2, 2.4, 5.0]
    def f(t):
        img = base.copy(); d = ImageDraw.Draw(img)
        for i, ((h, sub, _), pic, x, a) in enumerate(zip(panels, pics, xs, appear)):
            e = ease((t - a) / 0.35)
            if e <= 0: continue
            y = 260 + int((1 - e) * 40)
            p = pic if i < 2 else pic.rotate(-4 * e, expand=False, fillcolor=(20, 26, 60))
            sh = Image.new("RGBA", (P + 60, P + 60), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((30, 40, P + 30, P + 40), 24, fill=(0, 0, 0, int(140 * e)))
            img.paste(sh.filter(ImageFilter.GaussianBlur(18)), (x - 30, y - 30), sh.filter(ImageFilter.GaussianBlur(18)))
            m = Image.new("L", (P, P), 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, P - 1, P - 1), 24, fill=int(255 * e))
            img.paste(p, (x, y), m)
            col = (255, 214, 92) if i == 2 else (255, 255, 255)
            d.text((x, y - 120), h, font=font(64), fill=col)
            if sub: d.text((x, y - 48), sub, font=font(34, False), fill=(205, 212, 240))
        return img
    write("owl", f, 9.0)


def reel():
    pic = Image.open(G / "reel.png").convert("RGB")
    def f(t):
        img = cover(pic, W, H, 1.04 + 0.04 * t / 8, 0.5, 0.5); d = ImageDraw.Draw(img, "RGBA")
        # 진행 막대: 앞으로 갔다가 뒤로 휙, 되풀이
        cyc = (t * 1.6) % 1.0
        pos = 0.25 + 0.35 * (cyc / 0.7 if cyc < 0.7 else 1 - (cyc - 0.7) / 0.3)
        x0, x1, y = 360, 1560, 860
        d.rounded_rectangle((x0, y - 6, x1, y + 6), 6, fill=(255, 255, 255, 90))
        d.rounded_rectangle((x0, y - 6, x0 + int((x1 - x0) * pos), y + 6), 6, fill=(255, 64, 96, 255))
        cx = x0 + int((x1 - x0) * pos); d.ellipse((cx - 16, y - 16, cx + 16, y + 16), fill=(255, 255, 255, 255))
        n = min(47, 1 + int(46 * ease(t / 6.5)))
        tx = f"Rewind #{n}"; fnt = font(96)
        tw = d.textlength(tx, font=fnt)
        d.rounded_rectangle((W - tw - 150, 70, W - 70, 210), 30, fill=(10, 14, 40, 200))
        d.text((W - tw - 110, 82), tx, font=fnt, fill=(255, 214, 92) if n == 47 else (255, 255, 255))
        return img
    write("reel", f, 8.0)


def screw():
    pic = Image.open(G / "screw.png").convert("RGB")
    def f(t):
        img = cover(pic, W, H, 1.0 + 0.05 * ease(t / 7), 0.62, 0.7); d = ImageDraw.Draw(img, "RGBA")
        e1 = ease((t - 0.4) / 0.4)
        if e1 > 0:
            d.rounded_rectangle((70, 120, 860, 250), 28, fill=(10, 14, 40, int(210 * e1)))
            d.text((110, 142), "Step 14 of 14: Done ✓", font=font(64), fill=(255, 255, 255, int(255 * e1)))
        e2 = ease((t - 2.6) / 0.4)
        if e2 > 0:
            cx, cy, r = 1205, 800, int(95 + 30 * (1 - e2))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 64, 96, int(255 * e2)), width=10)
            d.rounded_rectangle((70, 280, 900, 400), 28, fill=(255, 64, 96, int(225 * e2)))
            d.text((110, 300), "...so where does this go?", font=font(60), fill=(255, 255, 255, int(255 * e2)))
        return img
    write("screw", f, 7.0)


if __name__ == "__main__":
    owl(); reel(); screw()
    for n in ("owl", "reel", "screw"):
        print(n, (G / f"{n}.mp4").stat().st_size)
