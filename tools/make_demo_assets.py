"""Ассеты демо типов роликов (ROADMAP C2) — всё нарисовано кодом, детерминированно, лицензия своя (CC0).

    python tools/make_demo_assets.py            # перезаписать tests/fixtures/kinds/<тип>/assets/
    python tools/make_demo_assets.py library data-story   # только эти наборы (ROADMAP C4)

promo — 3 фото настольной лампы и логотип; slideshow — 4 пейзажа и вырезанный объект (параллакс); tutorial — запись
экрана (форма, курсор, ввод, клик); clip — «подкаст» (два собеседника, звук — синтетическая речь, не голос человека);
data-story — CSV с выдуманными данными; library (фикстура галереи C4, tests/fixtures/library/) — портрет-аватар
и CSV; фото, логотип, запись экрана и «подкаст» библиотеки — копии из демо promo, tutorial и clip.
Файлы маленькие (JPG q82, видео crf 30): они лежат в git. Запускать только при намеренной смене демо.
"""
from __future__ import annotations

import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FONT = ROOT / "assets" / "fonts" / "Manrope-VF.ttf"
DEMOS = ROOT / "tests" / "fixtures" / "kinds"


def font(size):
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_axes([700])
    except (OSError, AttributeError):
        pass
    return f


def gradient(w, h, top, bot):
    a = np.linspace(0, 1, h)[:, None, None]
    arr = (np.array(top)[None, None, :] * (1 - a) + np.array(bot)[None, None, :] * a).repeat(w, 1)
    return Image.fromarray(arr.astype(np.uint8))


def soft(img, r):
    return img.filter(ImageFilter.GaussianBlur(r))


# ------------------------------------------------------------------ promo: лампа и логотип
def lamp(w, h, bg_top, bg_bot, angle=0.0, lit=False):
    img = gradient(w, h, bg_top, bg_bot).convert("RGBA")
    d = ImageDraw.Draw(img)
    cx, base_y = w * 0.5, h * 0.84
    # тень на столе
    sh = Image.new("L", (w, h), 0)
    ImageDraw.Draw(sh).ellipse((cx - w * 0.3, base_y - h * 0.03, cx + w * 0.3, base_y + h * 0.04), fill=120)
    img.paste((0, 0, 0), (0, 0), soft(sh, 18))
    if lit:  # конус света
        cone = Image.new("L", (w, h), 0)
        hx, hy = cx + w * 0.16 * math.cos(angle), h * 0.32
        ImageDraw.Draw(cone).polygon([(hx - w * 0.08, hy + 30), (hx + w * 0.08, hy + 30), (hx + w * 0.36, base_y),
                                      (hx - w * 0.36, base_y)], fill=110)
        img.paste((255, 226, 160), (0, 0), soft(cone, 40))
    metal, dark = (232, 236, 242), (60, 66, 80)
    d.ellipse((cx - w * 0.17, base_y - h * 0.035, cx + w * 0.17, base_y + h * 0.02), fill=dark)  # основание
    jx, jy = cx - w * 0.06, h * 0.5
    d.line((cx, base_y - h * 0.02, jx, jy), fill=metal, width=int(w * 0.022))   # нижнее плечо
    hx, hy = cx + w * 0.16 * math.cos(angle), h * 0.3
    d.line((jx, jy, hx, hy), fill=metal, width=int(w * 0.02))                    # верхнее плечо
    d.ellipse((jx - 14, jy - 14, jx + 14, jy + 14), fill=dark)
    shade = [(hx - w * 0.04, hy - h * 0.04), (hx + w * 0.05, hy - h * 0.035), (hx + w * 0.11, hy + h * 0.05),
             (hx - w * 0.11, hy + h * 0.05)]
    d.polygon(shade, fill=(245, 166, 35))
    d.line(shade[:2], fill=(255, 210, 120), width=6)
    if lit:
        d.ellipse((hx - w * 0.05, hy + h * 0.03, hx + w * 0.05, hy + h * 0.07), fill=(255, 250, 220))
    return img.convert("RGB")


def logo(path):
    w, h = 900, 300
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((20, 40, 240, 260), fill=(245, 166, 35, 255))
    d.ellipse((70, 90, 190, 210), fill=(0, 0, 0, 0))
    d.pieslice((20, 40, 240, 260), 200, 340, fill=(255, 214, 120, 255))
    f = font(150)
    d.text((280, 50), "AURORA", font=f, fill=(255, 255, 255, 255))
    img.save(path)


# ------------------------------------------------------------------ slideshow: пейзажи
def landscape(w, h, sky, sun, layers, seed):
    rng = np.random.default_rng(seed)
    img = gradient(w, h, sky[0], sky[1]).convert("RGBA")
    d = ImageDraw.Draw(img)
    if sun:
        g = Image.new("L", (w, h), 0)
        ImageDraw.Draw(g).ellipse((sun[0] - 220, sun[1] - 220, sun[0] + 220, sun[1] + 220), fill=150)
        img.paste(sun[2], (0, 0), soft(g, 80))
        d.ellipse((sun[0] - 70, sun[1] - 70, sun[0] + 70, sun[1] + 70), fill=sun[2])
    for i, (yb, amp, colr) in enumerate(layers):
        xs = np.linspace(0, w, 40)
        ph = rng.uniform(0, 6.28, 3)
        ys = h * yb - amp * h * (0.5 + 0.3 * np.sin(xs / w * 6 + ph[0]) + 0.2 * np.sin(xs / w * 15 + ph[1]))
        d.polygon([(0, h)] + list(zip(xs, ys)) + [(w, h)], fill=colr)
    return img.convert("RGB")


def bird(path):
    w, h = 900, 600
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, (x, y, s) in enumerate(((300, 260, 1.0), (520, 200, 0.7), (640, 330, 0.55))):
        pts = [(x - 120 * s, y - 10 * s), (x - 40 * s, y - 50 * s), (x, y), (x + 40 * s, y - 50 * s),
               (x + 120 * s, y - 10 * s), (x + 40 * s, y - 25 * s), (x, y + 18 * s), (x - 40 * s, y - 25 * s)]
        d.polygon(pts, fill=(25, 22, 40, 255))
    img.save(path)


# ------------------------------------------------------------------ tutorial: запись экрана
def screen_video(path, w=1280, h=720, fps=30, secs=10.0):
    n = int(fps * secs)
    f_ui, f_small, f_big = font(26), font(20), font(34)
    text = "Weekly report"
    cur = lambda k: ((200 + 600 * k, 600 - 330 * k))  # noqa: E731
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "30",
                          "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    for i in range(n):
        t = i / fps
        img = Image.new("RGB", (w, h), (246, 247, 250))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, 240, h), fill=(32, 36, 48))
        for j, item in enumerate(("Home", "Reports", "Team", "Settings")):
            if j == 1:
                d.rounded_rectangle((16, 92 + j * 56, 224, 136 + j * 56), 10, fill=(64, 92, 230))
            d.text((36, 100 + j * 56), item, font=f_ui, fill=(235, 238, 245))
        d.text((290, 50), "New report", font=f_big, fill=(30, 34, 46))
        d.text((290, 130), "Title", font=f_small, fill=(110, 116, 130))
        d.rounded_rectangle((290, 160, 900, 220), 10, fill=(255, 255, 255), outline=(200, 205, 215), width=2)
        typed = text[:max(0, min(len(text), int((t - 3.0) * 6)))] if t > 3.0 else ""
        d.text((310, 175), typed + ("|" if 3.0 < t < 6.5 and int(t * 2) % 2 == 0 else ""), font=f_ui,
               fill=(30, 34, 46))
        d.text((290, 250), "Period", font=f_small, fill=(110, 116, 130))
        d.rounded_rectangle((290, 280, 900, 340), 10, fill=(255, 255, 255), outline=(200, 205, 215), width=2)
        d.text((310, 295), "Last 7 days", font=f_ui, fill=(30, 34, 46))
        pressed = 7.0 <= t < 7.25
        d.rounded_rectangle((290, 400, 520, 460), 12, fill=(44, 70, 200) if pressed else (64, 92, 230))
        d.text((330, 413), "Create", font=f_ui, fill=(255, 255, 255))
        if t >= 7.4:
            k = min(1.0, (t - 7.4) / 0.4)
            d.rounded_rectangle((900, 620 + 40 * (1 - k), 1240, 690 + 40 * (1 - k)), 12, fill=(40, 170, 90))
            d.text((925, 637 + 40 * (1 - k)), "Report created", font=f_ui, fill=(255, 255, 255))
        if t < 2.5:
            x, y = cur(min(1.0, t / 2.0) * 0.55)
        elif t < 6.5:
            x, y = cur(0.55)
        else:
            k = min(1.0, (t - 6.5) / 0.5)
            x, y = 530 - 130 * k + 200 * (1 - k) * 0, 345 + 85 * k
        d.polygon([(x, y), (x, y + 30), (x + 8, y + 23), (x + 14, y + 36), (x + 19, y + 34), (x + 13, y + 21),
                   (x + 23, y + 21)], fill=(20, 20, 20), outline=(255, 255, 255))
        p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()


# ------------------------------------------------------------------ clip: «подкаст»
def speechlike(secs, seed, sr=48000):
    """Синтетическая «речь»: слоги — гармонический тон с огибающей, слова — паузы. Не голос человека."""
    rng = np.random.default_rng(seed)
    n = int(secs * sr)
    out = np.zeros(n, np.float32)
    t = 0.25
    while t < secs - 0.4:
        for _ in range(rng.integers(2, 5)):  # слоги слова
            d = rng.uniform(0.12, 0.22)
            a0, a1 = int(t * sr), int(min(secs, t + d) * sr)
            tt = np.arange(a1 - a0) / sr
            f0 = rng.uniform(110, 170) * (1 + 0.08 * np.sin(2 * np.pi * 3 * tt))
            ph = 2 * np.pi * np.cumsum(f0) / sr
            v = sum(np.sin(k * ph) / k for k in range(1, 9))
            env = np.sin(np.pi * np.clip(tt / d, 0, 1)) ** 1.5
            out[a0:a1] += (0.22 * v * env).astype(np.float32)
            t += d
        t += rng.uniform(0.12, 0.45)
    return out


def podcast(path, w=960, h=540, fps=30, secs=10.0):
    sr = 48000
    a = speechlike(secs, 11)
    wav = path.with_suffix(".tmp.wav")
    with wave.open(str(wav), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes())
    env = np.array([float(np.sqrt(np.mean(a[int(i / fps * sr):int((i + 1) / fps * sr)] ** 2) + 1e-12))
                    for i in range(int(secs * fps))])
    env = env / env.max()
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "slow", "-crf", "30",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
                          str(path)], stdin=subprocess.PIPE)
    bg = gradient(w, h, (34, 28, 52), (14, 12, 22))
    for i in range(int(secs * fps)):
        img = bg.copy()
        d = ImageDraw.Draw(img)
        for j, (cx, colr) in enumerate(((w * 0.32, (245, 166, 35)), (w * 0.68, (79, 209, 197)))):
            talk = j == 0
            r = 110 + (14 * env[i] if talk else 0)
            d.ellipse((cx - r - 10, h * 0.45 - r - 10, cx + r + 10, h * 0.45 + r + 10),
                      outline=colr if talk and env[i] > 0.2 else (70, 70, 90), width=6)
            d.ellipse((cx - 100, h * 0.45 - 100, cx + 100, h * 0.45 + 100), fill=tuple(c // 2 for c in colr))
            d.ellipse((cx - 38, h * 0.45 - 60, cx + 38, h * 0.45 + 16), fill=colr)
            d.pieslice((cx - 80, h * 0.45 + 20, cx + 80, h * 0.45 + 180), 180, 360, fill=colr)
        d.rounded_rectangle((w / 2 - 14, h * 0.78, w / 2 + 14, h * 0.88), 12, fill=(200, 200, 210))
        p.stdin.write(img.tobytes())
    p.stdin.close()
    p.wait()
    wav.unlink()


def portrait(path, s=480):
    """Аватар: силуэт головы и плеч на градиенте (не человек)."""
    img = gradient(s, s, (120, 170, 220), (60, 90, 150)).convert("RGBA")
    d = ImageDraw.Draw(img)
    d.ellipse((s * .3, s * .16, s * .7, s * .6), fill=(244, 214, 190))
    d.ellipse((s * .27, s * .1, s * .73, s * .38), fill=(70, 50, 40))
    d.ellipse((s * .12, s * .62, s * .88, s * 1.4), fill=(40, 60, 90))
    soft(img, 1).convert("RGB").save(path, quality=86)


CSV = {
    # выдуманные данные для демо (не статистика): у CSV те же правила, что у фото, — запись в assets.yaml
    "data-story/assets/screen-time.csv": "age,hours per day\n13-17,7.2\n18-24,6.4\n25-34,5.1\n35-44,4.3\n45-54,3.6\n55+,2.9\n",
    "data-story/assets/by-year.csv": "year;hours\n2019;3.1\n2020;4.4\n2021;4.2\n2022;4.6\n2023;4.9\n2024;5.2\n",
    "../library/assets/sales.csv": "month,sales\nJan,1240\nFeb,1380\nMar,1710\nApr,1650\nMay,2120\nJun,2480\n",
}


def library():
    out = DEMOS.parent / "library" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    portrait(out / "avatar.jpg")
    for name in ("lamp-front.jpg", "logo.png"):
        (out / name).write_bytes((DEMOS / "promo" / "assets" / name).read_bytes())
    (out / "screen.mp4").write_bytes((DEMOS / "tutorial" / "assets" / "screen.mp4").read_bytes())
    (out / "podcast.mp4").write_bytes((DEMOS / "clip" / "assets" / "podcast.mp4").read_bytes())


def csvs(prefix):
    for rel, text in CSV.items():
        if rel.startswith(prefix):
            f = DEMOS / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8", newline="\n")


def main(only=()):
    if only:
        for name in only:
            if name == "library":
                library()
                csvs("../library")
            else:
                csvs(name)
        return
    out = DEMOS / "promo" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    lamp(900, 1100, (250, 236, 220), (226, 204, 182)).save(out / "lamp-front.jpg", quality=82)
    lamp(900, 1100, (220, 230, 240), (180, 196, 214), angle=0.9).save(out / "lamp-side.jpg", quality=82)
    lamp(900, 1100, (40, 36, 52), (20, 18, 28), lit=True).save(out / "lamp-night.jpg", quality=82)
    logo(out / "logo.png")
    out = DEMOS / "slideshow" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    landscape(1600, 1000, ((255, 190, 140), (120, 80, 140)), (1100, 520, (255, 236, 200)),
              [(0.75, 0.25, (90, 60, 110)), (0.9, 0.2, (50, 34, 70)), (1.02, 0.15, (24, 18, 36))], 1) \
        .save(out / "dusk.jpg", quality=82)
    landscape(1600, 1000, ((150, 205, 240), (225, 240, 250)), (400, 250, (255, 255, 235)),
              [(0.7, 0.3, (130, 160, 190)), (0.85, 0.22, (70, 120, 110)), (1.0, 0.15, (40, 80, 60))], 2) \
        .save(out / "valley.jpg", quality=82)
    landscape(1600, 1000, ((30, 40, 80), (90, 70, 130)), (1250, 260, (240, 240, 255)),
              [(0.8, 0.2, (40, 40, 80)), (0.95, 0.12, (20, 20, 45))], 3).save(out / "night.jpg", quality=82)
    landscape(1600, 1000, ((255, 225, 160), (250, 170, 110)), (800, 640, (255, 245, 210)),
              [(0.85, 0.08, (60, 110, 160)), (1.0, 0.1, (30, 70, 120))], 4).save(out / "sea.jpg", quality=82)
    bird(out / "birds.png")
    out = DEMOS / "tutorial" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    screen_video(out / "screen.mp4")
    out = DEMOS / "clip" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    podcast(out / "podcast.mp4")
    csvs("data-story")
    library()
    csvs("../library")
    for f in sorted(DEMOS.glob("*/assets/*")):
        print(f"{f.relative_to(ROOT)}: {f.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main(sys.argv[1:])
