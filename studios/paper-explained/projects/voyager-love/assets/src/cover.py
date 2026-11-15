"""Обложка voyager-love v2 — постер в мире ролика («Золотая пластинка»), 1080×1920.
Основа — арт s10 (Kie: золотая пластинка одна в космосе), пластинка крупно внизу; на ней — большое светящееся сердце,
сквозь него — золотая линия пульса (мотив ролика). Сверху — рукой «дальше всех от Земли летит» и заголовок
«ЗАПИСЬ СЕРДЦА / ВЛЮБЛЁННОЙ ЖЕНЩИНЫ» (Oswald, фольга). Всё важное — в центре 3:4 (сетка профиля TikTok и Instagram,
y 240…1680). Шаблон обложки бренда (brand/cover.yaml) рассчитан на бумагу — поэтому своя.
Первая версия (кадр крючка + текст снизу) пользователю не понравилась: «не красивая, сердце почти не видно».
    python studios/paper-explained/projects/voyager-love/assets/src/cover.py [--grid]
→ studios/paper-explained/output/voyager-love/voyager-love.cover.jpg (поверх обложки `package`);
  --grid — ещё превью с рамкой 3:4 в qa/cover_grid.jpg."""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

SRC = Path(__file__).parent
PROJ = SRC.parents[1]
STUDIO = PROJ.parents[1]
FONTS = STUDIO / "brand" / "fonts"
ART = PROJ / "assets" / "images" / "f0a93c2b9a862c69.png"  # s10: пластинка одна среди звёзд
OUT = STUDIO / "output" / "voyager-love" / "voyager-love.cover.jpg"
W, H = 1080, 1920
NAVY = (5, 7, 15)
CREAM = (244, 231, 200)
GOLD2 = (255, 231, 163)
FOIL = [(255, 246, 214), (255, 231, 163), (240, 196, 92), (201, 149, 47), (255, 225, 160), (214, 160, 58)]
HEART = [((60, 104), (20, 76), (4, 52), (4, 32)), ((4, 32), (4, 14), (18, 4), (32, 4)),
         ((32, 4), (44, 4), (54, 11), (60, 22)), ((60, 22), (66, 11), (76, 4), (88, 4)),
         ((88, 4), (102, 4), (116, 14), (116, 32)), ((116, 32), (116, 52), (100, 76), (60, 104))]  # тот же путь, что в сценах


def font(name, size, weight=None):
    f = ImageFont.truetype(str(FONTS / name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def layer():
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def glow(mask, color, radius, strength=1.0):
    g = Image.new("RGBA", (W, H), color + (0,))
    g.putalpha(mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v: min(255, int(v * strength))))
    return g


def background():
    art = Image.open(ART).convert("RGB")
    s = 1.12  # пластинка ~950 px шириной
    art = art.resize((round(art.width * s), round(art.height * s)), Image.LANCZOS)
    cx, cy = 0.502 * art.width, 0.611 * art.height  # центр пластинки на арте
    x0, y0 = int(cx - W / 2), int(cy - 1250)          # центр пластинки — на y 1250
    img = art.crop((x0, y0, x0 + W, y0 + H)).filter(ImageFilter.UnsharpMask(2, 70, 2)).convert("RGBA")
    # верх темнее (под заголовок), лёгкая виньетка
    y = np.arange(H, dtype=np.float32)[:, None]
    x = np.arange(W, dtype=np.float32)[None, :]
    top = np.clip(1 - (y - 120) / 760, 0, 1) * 0.55
    vig = np.clip(((x - W / 2) / (W * .75)) ** 2 + ((y - H * .55) / (H * .62)) ** 2, 0, 1) ** 1.6 * 0.6
    a = np.clip(top + vig, 0, 0.9)
    sh = Image.new("RGBA", (W, H), NAVY + (0,))
    sh.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    img.alpha_composite(sh)
    return img


def heart_mask(cx, cy, w, ss=4):
    """Сердце шириной w с центром (cx, cy): кубические Безье пути сцен → многоугольник, сглаживание суперсэмплом."""
    k = w / 112
    pts = []
    for p0, p1, p2, p3 in HEART:
        for t in np.linspace(0, 1, 40):
            u = 1 - t
            px = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
            py = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
            pts.append(((cx + (px - 60) * k) * ss, (cy + (py - 54) * k) * ss))
    m = Image.new("L", (W * ss, H * ss), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    return m.resize((W, H), Image.LANCZOS)


def heart(img, cx, cy, w):
    m = heart_mask(cx, cy, w)
    img.alpha_composite(glow(m, (255, 140, 40), 90, 1.4))   # свет на пластинку
    img.alpha_composite(glow(m, (255, 170, 70), 36, 1.6))
    # заливка: радиальный градиент — светлое ядро слева сверху, к краям — насыщенный янтарь
    y = np.arange(H, dtype=np.float32)[:, None]
    x = np.arange(W, dtype=np.float32)[None, :]
    r = np.sqrt(((x - (cx - w * .12)) / w) ** 2 + ((y - (cy - w * .14)) / w) ** 2)
    t = np.clip(r / .62, 0, 1)[..., None]
    c0, c1, c2 = np.array([255, 236, 190.]), np.array([255, 166, 72.]), np.array([232, 104, 30.])
    col = np.where(t < .5, c0 + (c1 - c0) * (t / .5), c1 + (c2 - c1) * ((t - .5) / .5))
    fill = Image.fromarray(np.broadcast_to(col, (H, W, 3)).astype(np.uint8)).convert("RGBA")
    fill.putalpha(m)
    img.alpha_composite(fill)
    # блик: мягкое светлое пятно на левой «доле» — сердце светится изнутри, а не плоская наклейка
    hl = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hl).ellipse((cx - w * .36, cy - w * .40, cx - w * .02, cy - w * .10), fill=255)
    hl = ImageChops.multiply(hl.filter(ImageFilter.GaussianBlur(w * .07)), m)
    spot = Image.new("RGBA", (W, H), (255, 250, 230, 0))
    spot.putalpha(hl.point(lambda v: int(v * .55)))
    img.alpha_composite(spot)
    # светлая кромка по контуру
    edge = ImageChops.subtract(m, m.filter(ImageFilter.MinFilter(7)))
    rim = Image.new("RGBA", (W, H), (255, 240, 200, 0))
    rim.putalpha(edge.point(lambda v: int(v * .8)))
    img.alpha_composite(rim)


def pulse(img, y0, cx, hw):
    """Линия пульса через весь кадр: ровно — зубец — сердце (разрыв hw вокруг cx) — зубец — ровно, концы гаснут."""
    def seg(xa, xb, flip):
        pts = []
        for x in np.arange(xa, xb + 1, 2.0):
            u = (x - xa) / (xb - xa)
            v = 0.0
            for c, a, s in ((.35, -10, .03), (.62, 70, .012), (.66, -150, .014), (.70, 40, .012), (.82, -16, .035)):
                v += a * np.exp(-((u - c) / s) ** 2)
            if flip:
                v = v
            pts.append((x, y0 + v))
        return pts
    ss = 3
    m = Image.new("L", (W * ss, H * ss), 0)
    d = ImageDraw.Draw(m)
    for pts in (seg(30, cx - hw, False), [(x, y) for x, y in seg(cx + hw, W - 30, False)]):
        d.line([(x * ss, y * ss) for x, y in pts], fill=255, width=6 * ss, joint="curve")
    m = m.resize((W, H), Image.LANCZOS)
    fade = np.clip(np.minimum(np.arange(W) - 30, W - 30 - np.arange(W)) / 160, 0, 1).astype(np.float32)
    m = Image.fromarray((np.asarray(m, np.float32) * fade[None, :]).astype(np.uint8))
    img.alpha_composite(glow(m, (233, 160, 60), 22, 2.2))
    img.alpha_composite(glow(m, (255, 210, 130), 6, 2.0))
    core = Image.new("RGBA", (W, H), (255, 246, 220, 0))
    core.putalpha(m)
    img.alpha_composite(core)


def text_mask(text, f, cy, tracking=0):
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    if tracking:
        widths = [d.textlength(ch, font=f) for ch in text]
        total = sum(widths) + tracking * (len(text) - 1)
        x = (W - total) / 2
        b = d.textbbox((0, 0), text, font=f)
        y = cy - (b[3] + b[1]) / 2
        for ch, wd in zip(text, widths):
            d.text((x, y), ch, font=f, fill=255)
            x += wd + tracking
    else:
        b = d.textbbox((0, 0), text, font=f)
        d.text(((W - (b[2] - b[0])) / 2 - b[0], cy - (b[3] + b[1]) / 2), text, font=f, fill=255)
    return m


def foil(img, text, f, cy):
    m = text_mask(text, f, cy)
    x0, y0, x1, y1 = m.getbbox()
    img.alpha_composite(glow(m, (233, 185, 73), 30, .7))
    sh = Image.new("RGBA", (W, H), (36, 20, 2, 0))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(1.5)))
    img.alpha_composite(sh, (0, 7))
    ys = np.linspace(0, 1, y1 - y0)
    stops = np.linspace(0, 1, len(FOIL))
    grad = np.stack([np.interp(ys, stops, [c[i] for c in FOIL]) for i in range(3)], 1)
    g = np.zeros((H, W, 3), np.uint8)
    g[y0:y1] = grad[:, None, :].astype(np.uint8)
    fill = Image.fromarray(g).convert("RGBA")
    fill.putalpha(m)
    img.alpha_composite(fill)


def plain(img, text, f, cy, color, tracking=0, glow_col=None):
    m = text_mask(text, f, cy, tracking)
    if glow_col:
        img.alpha_composite(glow(m, glow_col, 16, .9))
    sh = Image.new("RGBA", (W, H), NAVY + (0,))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(3)))
    img.alpha_composite(sh, (0, 5))
    fill = Image.new("RGBA", (W, H), color + (0,))
    fill.putalpha(m)
    img.alpha_composite(fill)


def grain(img, amount=7):
    rng = np.random.default_rng(7)
    a = np.asarray(img.convert("RGB"), np.int16) + rng.normal(0, amount, (H, W, 1)).astype(np.int16)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def main():
    img = background()
    hx, hy, hw = 540, 1250, 350      # сердце — на центре пластинки
    pulse(img, hy + 8, hx, hw * .62)
    heart(img, hx, hy, hw)
    plain(img, "дальше всех от Земли летит", font("Caveat-VF.ttf", 84, 700), 318, GOLD2, glow_col=(233, 185, 73))
    plain(img, "ЗАПИСЬ СЕРДЦА", font("Oswald-VF.ttf", 112, 500), 450, CREAM, tracking=6)
    foil(img, "ВЛЮБЛЁННОЙ", font("Oswald-VF.ttf", 148, 700), 610)
    foil(img, "ЖЕНЩИНЫ", font("Oswald-VF.ttf", 148, 700), 772)
    # строку телеметрии бирюзой убрали: пользователь — «почти не видно, портит картинку»
    img = grain(img)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(OUT, "JPEG", quality=93, optimize=True)
    print(OUT)
    if "--grid" in sys.argv:
        g = img.convert("RGB")
        ImageDraw.Draw(g).rectangle((0, 240, W - 1, 1679), outline=(255, 0, 0), width=4)
        g.save(PROJ / "qa" / "cover_grid.jpg", quality=85)


if __name__ == "__main__":
    main()
