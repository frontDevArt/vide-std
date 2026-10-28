"""Логотип Yereva: иконка, надпись, аватарка — SVG и PNG из одной геометрии.

Геометрия иконки снята с прототипа (Gemini, 2026-10-28) и выровнена: наклон всех косых граней 0.6,
одинаковая толщина рукавов и ножки, одинаковый белый зазор. Надпись — Outfit (OFL, fonts/).

    python docs/agency/brand-yereva/make_logo.py        # нужен fonttools
"""
import math
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONT = HERE / "fonts" / "Outfit-VF.ttf"
OUT = HERE / "out"

BLUE, INK, WHITE = "#2266ED", "#1A1A18", "#FFFFFF"
SS = 4  # суперсэмплинг PNG

# --- иконка (единицы прототипа, центр x = 0, верх рукавов y = 0, y вниз) ---
K = 0.6                       # наклон косых граней
COS = 1 / math.sqrt(1 + K * K)
X_OUT = 369                   # внешний край рукава
ARM = 208                     # толщина рукава по вертикали
STEM = round(ARM * COS)       # ширина ножки = толщине рукава поперёк (178)
STEM_BOTTOM = 515             # низ ножки у внешнего края
SUN_CY, SUN_R = 122, 243      # полукруг: центр и радиус
GAP = 48                      # белый зазор (основной логотип)
GAP_AVATAR = 84               # зазор аватарки: на 110 px тонкий пропадает


def icon_shapes(gap=GAP, scale=1.0, ox=0.0, oy=0.0, roles=("ink", "blue")):
    """Фигуры иконки в координатах холста: [{"role", "poly", "d"}]."""
    def P(x, y):
        return (ox + x * scale, oy + y * scale)

    xi = gap / 2
    xs = xi + STEM
    top = lambda ax: K * (X_OUT - ax)              # верхняя грань рукава на |x| = ax
    left = [(-X_OUT, 0), (-xi, top(xi)), (-xi, STEM_BOTTOM + K * STEM),
            (-xs, STEM_BOTTOM), (-xs, top(xs) + ARM), (-X_OUT, ARM)]
    right = [(-x, y) for x, y in reversed(left)]
    shapes = [_poly(roles[0], [P(*p) for p in pts]) for pts in (left, right)]

    # полукруг над V: круг, срезанный линией, параллельной рукавам, на зазор выше
    apex = top(0) - gap / COS
    # x^2 + (apex - K x - cy)^2 = r^2  →  точка пересечения справа
    a, b, c = 1 + K * K, -2 * K * (apex - SUN_CY), (apex - SUN_CY) ** 2 - SUN_R ** 2
    x1 = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    y1 = apex - K * x1
    t0 = math.atan2(y1 - SUN_CY, -x1)     # y вниз: от t0 к t1 через −π/2 — верх круга
    t1 = math.atan2(y1 - SUN_CY, x1)
    arc = [(SUN_R * math.cos(t), SUN_CY + SUN_R * math.sin(t))
           for t in (t0 + (t1 - t0) * i / 180 for i in range(181))]
    sun = [P(*p) for p in arc] + [P(0, apex)]
    (sx0, sy0), (sx1, sy1), (axp, ayp) = P(-x1, y1), P(x1, y1), P(0, apex)
    r = SUN_R * scale
    d = (f"M{sx0:.2f} {sy0:.2f}A{r:.2f} {r:.2f} 0 0 1 {sx1:.2f} {sy1:.2f}"
         f"L{axp:.2f} {ayp:.2f}Z")
    shapes.append({"role": roles[1], "poly": sun, "d": d})
    return shapes


def icon_bbox(gap=GAP):
    pts = [p for s in icon_shapes(gap) for p in s["poly"]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _poly(role, pts):
    d = "M" + "L".join(f"{x:.2f} {y:.2f}" for x, y in pts) + "Z"
    return {"role": role, "poly": pts, "d": d}


# --- надпись ---
_fonts = {}


def _font(wght):
    if wght not in _fonts:
        _fonts[wght] = instantiateVariableFont(TTFont(FONT), {"wght": wght})
    return _fonts[wght]


def word_shapes(text, wght, cap, x0, base, tracking=-0.01, blue_last=True):
    """Надпись с высотой прописной cap, левый край x0, базовая линия base."""
    f = _font(wght)
    upm = f["head"].unitsPerEm
    s = cap / f["OS/2"].sCapHeight
    cmap, gs, hmtx = f.getBestCmap(), f.getGlyphSet(), f["hmtx"]
    shapes, x = [], x0
    for i, ch in enumerate(text):
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (s, 0, 0, -s, x, base)))
        role = "blue" if blue_last and i == len(text) - 1 else "ink"
        shapes.append({"role": role, "d": pen.getCommands(), "glyph": (ch, x, base, s * upm, wght)})
        x += (hmtx[name][0] + tracking * upm) * s
    return shapes, x - x0 - tracking * upm * s


# --- раскладки ---
def lockup_vertical():
    x0, y0, x1, y1 = icon_bbox()
    ih = y1 - y0
    cap = 0.323 * ih                      # пропорции прототипа: надпись 240 при иконке 743
    _, w = word_shapes("Yereva", 700, cap, 0, 0)
    W = max(x1 - x0, w)
    ox = W / 2
    shapes = icon_shapes(ox=ox, oy=-y0)
    base = ih + 0.155 * ih + cap
    ws, _ = word_shapes("Yereva", 700, cap, ox - w / 2, base)
    return shapes + ws, W, base


def lockup_horizontal():
    x0, y0, x1, y1 = icon_bbox()
    ih, iw = y1 - y0, x1 - x0
    cap = 0.40 * ih
    _, w = word_shapes("Yereva", 600, cap, 0, 0)
    space = 0.26 * ih
    shapes = icon_shapes(ox=-x0, oy=-y0)
    base = ih / 2 + cap / 2
    ws, _ = word_shapes("Yereva", 600, cap, iw + space, base)
    return shapes + ws, iw + space + w, ih


def lockup_icon(gap=GAP):
    x0, y0, x1, y1 = icon_bbox(gap)
    return icon_shapes(gap, ox=-x0, oy=-y0), x1 - x0, y1 - y0


def avatar_shapes(size=1080, fill=0.70):
    """Белая иконка с толстым зазором на синем квадрате; помещается в круг аватарки."""
    x0, y0, x1, y1 = icon_bbox(GAP_AVATAR)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    pts = [p for s in icon_shapes(GAP_AVATAR) for p in s["poly"]]
    rmax = max(math.hypot(x - cx, y - cy) for x, y in pts)
    sc = fill * (size / 2) / rmax
    return icon_shapes(GAP_AVATAR, sc, size / 2 - cx * sc, size / 2 - cy * sc, roles=("ink", "ink"))


# --- вывод ---
def colors(theme):
    """theme: dark — тёмные буквы для светлого фона; light — белые для тёмного; avatar — белое на синем."""
    return {"dark": {"ink": INK, "blue": BLUE},
            "light": {"ink": WHITE, "blue": BLUE},
            "avatar": {"ink": WHITE, "blue": WHITE}}[theme]


def write_svg(path, shapes, w, h, theme, pad=0.0, bg=None):
    col = colors(theme)
    P = pad * max(w, h)
    W, H = w + 2 * P, h + 2 * P
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H:.1f}" '
           f'width="{W:.0f}" height="{H:.0f}">']
    if bg:
        out.append(f'<rect width="100%" height="100%" fill="{bg}"/>')
    out.append(f'<g transform="translate({P:.2f} {P:.2f})">')
    out += [f'<path fill="{col[s["role"]]}" d="{s["d"]}"/>' for s in shapes]
    out.append("</g></svg>")
    path.write_text("\n".join(out), encoding="utf-8")


def render(shapes, w, h, theme, width_px, pad=0.0, bg=None):
    """PNG той же геометрии: многоугольники иконки и глифы шрифта (FreeType) по тем же координатам."""
    col = colors(theme)
    P = pad * max(w, h)
    k = width_px / (w + 2 * P)
    Wpx, Hpx = round((w + 2 * P) * k), round((h + 2 * P) * k)
    im = Image.new("RGBA", (Wpx * SS, Hpx * SS), bg or (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    m = lambda x, y: ((x + P) * k * SS, (y + P) * k * SS)
    for s in shapes:
        if "glyph" in s:
            ch, x, base, size, wght = s["glyph"]
            f = ImageFont.truetype(str(FONT), max(1, round(size * k * SS)))
            f.set_variation_by_axes([wght])
            d.text(m(x, base), ch, font=f, fill=col[s["role"]], anchor="ls")
        else:
            d.polygon([m(*p) for p in s["poly"]], fill=col[s["role"]])
    return im.resize((Wpx, Hpx), Image.LANCZOS)


def main():
    OUT.mkdir(exist_ok=True)
    v, vw, vh = lockup_vertical()
    hz, hw, hh = lockup_horizontal()
    ic, iw, ih = lockup_icon()
    av = avatar_shapes()

    for name, (sh, w, h) in {"logo": (v, vw, vh), "logo-horizontal": (hz, hw, hh),
                             "icon": (ic, iw, ih)}.items():
        write_svg(OUT / f"{name}.svg", sh, w, h, "dark", pad=0.04)
        write_svg(OUT / f"{name}-white.svg", sh, w, h, "light", pad=0.04)
    write_svg(OUT / "avatar.svg", av, 1080, 1080, "avatar", bg=BLUE)

    # бренд-кит студии: logo-dark — для светлого фона, logo-light — для тёмного (docs/BRAND.md)
    render(v, vw, vh, "dark", 1600, pad=0.04).save(OUT / "logo-dark.png")
    render(v, vw, vh, "light", 1600, pad=0.04).save(OUT / "logo-light.png")
    render(hz, hw, hh, "dark", 2000, pad=0.04).save(OUT / "logo-horizontal-dark.png")
    render(hz, hw, hh, "light", 2000, pad=0.04).save(OUT / "logo-horizontal-light.png")
    render(ic, iw, ih, "dark", 1024, pad=0.04).save(OUT / "icon.png")
    render(av, 1080, 1080, "avatar", 1080, bg=BLUE).save(OUT / "avatar-1080.png")
    sheet(v, vw, vh, hz, hw, hh, av)


def _circle(im):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, im.size[0] - 1, im.size[1] - 1), fill=255)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def sheet(v, vw, vh, hz, hw, hh, av):
    """Лист для просмотра: логотип на светлом и тёмном, горизонталь, аватарка в 110 px."""
    vd = render(v, vw, vh, "dark", 1100, pad=0.18, bg=WHITE)
    hd = render(hz, hw, hh, "dark", 1100, pad=0.12, bg=WHITE)
    top = 50 + vd.height + 50
    y = top + hd.height + 60
    S = Image.new("RGB", (2400, y + 560), "#F2F2F0")
    S.paste(vd, (50, 50))
    S.paste(render(v, vw, vh, "light", 1100, pad=0.18, bg=INK), (1250, 50))
    S.paste(hd, (50, top))
    S.paste(render(hz, hw, hh, "light", 1100, pad=0.12, bg=INK), (1250, top))
    big = _circle(render(av, 1080, 1080, "avatar", 440, bg=BLUE))
    S.paste(big, (50, y), big)
    for i, px in enumerate((110, 64, 40)):
        a = _circle(render(av, 1080, 1080, "avatar", px, bg=BLUE))
        S.paste(a, (560 + i * 160, y + 165), a)
    proto = _circle(render(avatar_like_prototype(), 1080, 1080, "avatar", 110, bg=BLUE))
    S.paste(proto, (1100, y + 165), proto)
    d = ImageDraw.Draw(S)
    lab = ImageFont.truetype("arial.ttf", 30)   # в Outfit нет кириллицы
    d.text((560, y + 300), "110 px      64 px      40 px", font=lab, fill=INK)
    d.text((1060, y + 300), "зазор 48 (было)", font=lab, fill=INK)
    S.save(OUT / "sheet.png")


def avatar_like_prototype():
    """Та же аватарка с тонким зазором прототипа — для сравнения на листе."""
    global GAP_AVATAR
    keep, GAP_AVATAR = GAP_AVATAR, GAP
    try:
        return avatar_shapes()
    finally:
        GAP_AVATAR = keep


if __name__ == "__main__":
    main()
