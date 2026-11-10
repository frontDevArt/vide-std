"""Аватар канала Paper Explained: ч/б полутоновая вырезка (Kie) на терракотовом круге и бумаге кита.

Запуск из корня репозитория:
  python studios/paper-explained/brand/make_avatar.py gen [имя …]      # ПЛАТНО: предметы Kie (12 кр за штуку) + rembg
  python studios/paper-explained/brand/make_avatar.py compose [имя …]  # бесплатно: сборка аватаров и листа превью

Предметы — brand/avatar/src/<имя>.png и .cut.png (есть файл — повтор бесплатен), учёт — brand/avatar/sources.json.
Аватары — brand/avatar/<имя>.png (1080×1080, площадка сама режет в круг), превью — brand/avatar/preview.png.
Букв на картинке нет: аватар в ленте — 40–100 px, читается только силуэт.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from studio import imagegen, workspace  # noqa: E402

OUT = HERE / "avatar"
SRC = OUT / "src"
MODEL, RESOLUTION = "nano-banana-2", "2K"
STYLE = ("Style: black and white editorial halftone cut-out, vintage magazine print, high contrast, visible halftone "
         "dots and ink imperfections, cleanly isolated subject with a thin white paper cut border, premium paper "
         "collage quality, flat even light. Isolated on a plain flat light grey background. No clutter, no text, no "
         "letters, no numbers, no logos, no watermark, no anime, no cartoon style, no CGI look, no glossy 3D "
         "rendering, no photorealistic background, no oversaturated colors, no distorted anatomy, no blurry details.")
# имя → (промпт предмета, поворот°, доля кадра по длинной стороне, сдвиг центра x/y в долях кадра)
SUBJECTS = {
    "scissors": ("a pair of vintage steel tailor scissors, half open, seen straight from above, blades pointing up",
                 -14, 0.80, (0.0, 0.0)),
    "plane": ("a single folded paper airplane made of plain blank white paper, flying upward to the right, "
              "three-quarter view from the side, simple bold silhouette", 0, 0.78, (0.0, -0.01)),
    "hand": ("a vintage engraving-style human hand with a shirt cuff, index finger pointing to the right, the other "
             "fingers folded, side view, simple bold silhouette", -10, 0.80, (0.0, 0.0)),
}
S = 1080
BORDER = 13  # px белой кромки вокруг предмета
PAPER, ACCENT, NAVY = (0xF6, 0xF0, 0xE2), (0xC4, 0x65, 0x57), (0x30, 0x35, 0x3C)


def gen(names):
    ws = workspace.studio("paper-explained")
    SRC.mkdir(parents=True, exist_ok=True)
    log_f = OUT / "sources.json"
    log = json.loads(log_f.read_text(encoding="utf-8")) if log_f.exists() else {}
    print("баланс Kie до:", imagegen.kie_balance(ws))
    for n in names:
        raw, cut = SRC / f"{n}.png", SRC / f"{n}.cut.png"
        if not raw.exists():
            prompt = f"{SUBJECTS[n][0]}. {STYLE}"
            r = imagegen.kie_task(MODEL, {"prompt": prompt, "aspect_ratio": "1:1", "output_format": "png",
                                          "resolution": RESOLUTION}, ws)
            urls = r["result"].get("resultUrls") or []
            if not urls:
                raise SystemExit(f"{n}: Kie задача {r['task']} без resultUrls")
            imagegen._save_png(imagegen._download(urls[0]), raw)
            log[n] = {"file": f"src/{n}.png", "source": f"Kie AI {MODEL} {RESOLUTION}",
                      "license": imagegen.license_of(MODEL), "prompt": prompt, "credits": r["credits"],
                      "task": r["task"]}
            log_f.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"{n}: сгенерировано, {r['credits']} кр")
        if not cut.exists():
            tmp = cut.with_name(cut.stem + ".part.png")
            cmd = [str(imagegen.rembg_python()), "-I", "-c", imagegen._REMBG_CODE, imagegen.REMBG_MODEL,
                   str(raw), str(tmp)]
            p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                               timeout=imagegen.REMBG_TIMEOUT, check=False)
            if p.returncode != 0 or not tmp.exists():
                raise SystemExit(f"{n}: rembg код {p.returncode}: {(p.stderr or p.stdout).strip()[-300:]}")
            tmp.replace(cut)
            print(f"{n}: вырезано")
    print("баланс Kie после:", imagegen.kie_balance(ws))


def _paper():
    p = Image.open(HERE / "paper.jpg").convert("RGB")
    x, y = (p.width - S) // 2, (p.height - S) // 2
    return p.crop((x, y, x + S, y + S))


def _halftone(mask):
    """Растр на круге: точки темнее краски, гуще к правому нижнему краю (как печать)."""
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    step = 20.0
    u, v = (xx + yy) / np.sqrt(2), (xx - yy) / np.sqrt(2)  # сетка под 45°
    du, dv = (u % step) - step / 2, (v % step) - step / 2
    grad = np.clip(((xx + yy) / (2 * S) - 0.5) * 2.2, 0, 1)  # 0 слева сверху → 1 справа снизу
    dots = (np.sqrt(du ** 2 + dv ** 2) < grad * step * 0.46).astype(np.float32)
    return Image.fromarray((dots * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7)), mask


def compose(name):
    _, rot, frac, (dx, dy) = SUBJECTS[name]
    bg = _paper()
    lum = np.asarray(bg.convert("L"), np.float32) / float(np.mean(np.asarray(bg.convert("L"))))  # зерно бумаги
    # терракотовый круг с зерном и растром
    R = int(S * 0.43)
    c = (S // 2, S // 2)
    mask = Image.new("L", (S * 2, S * 2), 0)
    ImageDraw.Draw(mask).ellipse([2 * (c[0] - R), 2 * (c[1] - R), 2 * (c[0] + R), 2 * (c[1] + R)], fill=255)
    mask = mask.resize((S, S), Image.LANCZOS)
    disc = np.clip(np.array(ACCENT, np.float32)[None, None, :] * lum[..., None], 0, 255)
    dots, _ = _halftone(mask)
    k = (np.asarray(dots, np.float32) / 255)[..., None] * 0.22
    disc = disc * (1 - k) + np.array((0x7A, 0x2E, 0x28), np.float32) * k
    bg.paste(Image.fromarray(disc.astype(np.uint8)), (0, 0), mask)
    # тонкое кольцо краской со сдвигом — «неприводка» печати
    ring = Image.new("RGBA", (S * 2, S * 2), (0, 0, 0, 0))
    r2 = R + 26
    ImageDraw.Draw(ring).ellipse([2 * (c[0] - r2) + 20, 2 * (c[1] - r2) + 14, 2 * (c[0] + r2) + 20,
                                  2 * (c[1] + r2) + 14], outline=NAVY + (150,), width=5)
    bg.paste(ring.resize((S, S), Image.LANCZOS), (0, 0), ring.resize((S, S), Image.LANCZOS))
    # предмет: обрезать по альфе, повернуть, вписать, тень
    cut = Image.open(SRC / f"{name}.cut.png").convert("RGBA")
    a = cut.getchannel("A").point(lambda v: 255 if v > 24 else 0)
    cut = cut.crop(a.getbbox())
    if rot:
        cut = cut.rotate(rot, resample=Image.BICUBIC, expand=True)
        cut = cut.crop(cut.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox())
    k = S * frac / max(cut.size)
    cut = cut.resize((round(cut.width * k), round(cut.height * k)), Image.LANCZOS)
    x, y = round(S / 2 + dx * S - cut.width / 2), round(S / 2 + dy * S - cut.height / 2)
    # белая кромка вырезки кодом: rembg местами съедает кромку модели — ровная подложка по расширенной альфе
    solid = Image.new("L", (S, S), 0)
    solid.paste(cut.getchannel("A").point(lambda v: 255 if v > 96 else 0), (x, y))
    edge = solid.filter(ImageFilter.MaxFilter(2 * BORDER + 1)).filter(ImageFilter.GaussianBlur(1.2))
    edge = edge.point(lambda v: 0 if v < 96 else min(255, (v - 96) * 4))
    sh = Image.new("L", (S, S), 0)
    sh.paste(edge, (12, 18))
    sh = sh.filter(ImageFilter.GaussianBlur(12)).point(lambda v: int(v * 0.42))
    bg.paste(Image.new("RGB", (S, S), (20, 18, 16)), (0, 0), sh)
    bg.paste(Image.new("RGB", (S, S), (0xFB, 0xF8, 0xF0)), (0, 0), edge)
    bg.paste(cut, (x, y), cut)
    out = OUT / f"{name}.png"
    bg.save(out)
    return out


def preview(names):
    """Лист: каждый вариант в круге 420 px и 96 px (как в ленте) на тёмном фоне TikTok."""
    W, H = 40 + 500 * len(names), 640
    sheet = Image.new("RGB", (W, H), (18, 18, 18))
    for i, n in enumerate(names):
        im = Image.open(OUT / f"{n}.png").convert("RGB")
        for size, pos in ((420, (60 + 500 * i, 40)), (96, (60 + 500 * i + 162, 500))):
            m = Image.new("L", (size * 4, size * 4), 0)
            ImageDraw.Draw(m).ellipse([0, 0, size * 4 - 1, size * 4 - 1], fill=255)
            sheet.paste(im.resize((size, size), Image.LANCZOS), pos, m.resize((size, size), Image.LANCZOS))
    sheet.save(OUT / "preview.png")
    return OUT / "preview.png"


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    names = sys.argv[2:] or list(SUBJECTS)
    bad = [n for n in names if n not in SUBJECTS]
    if cmd not in ("gen", "compose") or bad:
        raise SystemExit(f"{__doc__}\nимена: {', '.join(SUBJECTS)}" + (f"\nнет такого: {bad}" if bad else ""))
    if cmd == "gen":
        gen(names)
    else:
        have = [n for n in names if (SRC / f"{n}.cut.png").exists()]
        for n in have:
            print(compose(n))
        if have:
            print(preview(have))
