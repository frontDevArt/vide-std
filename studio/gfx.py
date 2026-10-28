"""Графика на PIL: шрифты, easing, спрайты с неоновым свечением, фон, иконки, смартфон.

Принцип скорости: всё дорогое (размытие, текст, иконки, карточки) рисуется ОДИН раз в спрайт
и кэшируется; в кадре — только композиция спрайтов. Фон зависит от ГЛОБАЛЬНОГО времени,
поэтому склейка сцен и глав бесшовна.
"""
from __future__ import annotations

import functools
import math
import os
import random
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import style as SM
# прогресс и кривые — studio/anim.py (P2.6); prog здесь — span(t, a, b): отрезок [a, b]
from .anim import clamp, ei, eio, eo, eob, lerp  # noqa: F401
from .anim import span as prog  # noqa: F401
from .style import (ASSETS, DEFAULT_FONT, MOOD_KEYS, MOODS, PALETTES, STYLES, Style,  # noqa: F401
                    hex_rgb, mood_colors)

# ------------------------------------------------------------------ style
# Палитры, пресеты и настроения — в studio/style.py (P2.2); имена остаются и здесь. Хелперы ниже принимают
# style=; без него — активный стиль (style.use). Кэши держат стиль в ключе.
def _st(style):
    return style or SM.active()


def __getattr__(name):
    """Совместимость: PAL / STYLE / FONT_FAMILY / STYLE_NAME / STYLE_KEY — снимки активного стиля (только чтение).
    Новый код берёт `self.style` (шаблон) или `ctx["style"]`."""
    st = SM.active()
    views = {"PAL": lambda: dict(st.pal), "STYLE": lambda: dict(st.preset), "FONT_FAMILY": lambda: st.font,
             "STYLE_NAME": lambda: st.palette, "STYLE_KEY": lambda: st.key}
    if name in views:
        return views[name]()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def set_palette(name, mood=None, overrides=None):
    """Старое имя: палитра + настроение при прежнем семействе шрифта."""
    return SM.use(Style(name, mood, tuple(sorted((overrides or {}).items())), SM.active().font))


def chapter_glow(spec, style=None):
    """script/chNN.yaml → glow: <настроение> | {cool: "#hex", warm: "#hex"} → (cool, warm) или None."""
    if not spec:
        return None
    if isinstance(spec, str):
        m = mood_colors(spec)
        return m["glow_cool"], m["glow_warm"]
    if isinstance(spec, dict) and set(spec) <= {"cool", "warm"}:
        pal = _st(style).pal
        return (hex_rgb(spec["cool"]) if "cool" in spec else pal.get("glow_cool", pal["accent"]),
                hex_rgb(spec["warm"]) if "warm" in spec else pal.get("glow_warm", pal["accent2"]))
    raise ValueError(f"glow: {spec!r} — нужно имя настроения или {{cool, warm}}")


def apply_style(style):
    """project.yaml → style: palette, mood, overrides, font → активный `Style` (его же и возвращает). Одна точка:
    layout, prepare (stills), воркеры рендера и qa зовут её одинаково — субтитры переносятся и меряются тем
    шрифтом, что рисуются."""
    return SM.use(style if isinstance(style, Style) else Style.from_cfg(style))


def col(c, a=255, style=None):
    """'cyan' | (r,g,b) | '#rrggbb' -> (r,g,b,a)"""
    return _st(style).col(c, a)


WEIGHTS = {"black": "Black", "extrabold": "ExtraBold", "bold": "Bold", "semibold": "SemiBold",
           "medium": "Medium", "regular": "Regular", "light": "Light"}
FALLBACKS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/Library/Fonts/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
             "C:/Windows/Fonts/arialbd.ttf"]


def _font_file(weight, family=None):
    """Файл шрифта семейства (по умолчанию — семейство активного стиля): семейство входит в ключ кэша."""
    return _font_file_for(weight, family or SM.active().font)


@functools.lru_cache(None)
def _font_file_for(weight, family):
    env = os.environ.get("STUDIO_FONT_" + weight.upper())
    if env and os.path.exists(env):
        return env
    try:
        r = subprocess.run(["fc-match", "-f", "%{file}", f"{family}:style={WEIGHTS.get(weight, 'Bold')}"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=10)
        if r.returncode == 0 and os.path.exists(r.stdout.strip()):
            return r.stdout.strip()
    except Exception:
        pass
    for p in FALLBACKS:
        if os.path.exists(p):
            return p
    raise RuntimeError("Не найден шрифт с кириллицей. Установите Inter или задайте STUDIO_FONT_BOLD.")


_font_file.cache_clear = _font_file_for.cache_clear  # selftest.pin_fonts: сброс после смены STUDIO_FONT_*

WEIGHT_NUM = {"black": 900, "extrabold": 800, "bold": 700, "semibold": 600, "medium": 500, "regular": 400, "light": 300}


# Раскладка текста одна на всех ОС: Pillow с raqm (обычно Linux) ставит кернинг иначе, чем без него (Windows),
# и кадры расходятся с golden. BASIC = как на Windows.
LAYOUT = ImageFont.Layout.BASIC


def font(size, weight="bold", family=None, style=None):
    """family: head | num | mono — шрифт роли из пресета (локальный файл из assets/). Без пресета — как раньше."""
    return _font(size, weight, family, _st(style))


@functools.lru_cache(None)
def _font(size, weight, family, style):
    rel = style.fonts.get(family or "head")
    if rel:
        f = ImageFont.truetype(os.path.join(ASSETS, rel), int(size), layout_engine=LAYOUT)
        try:
            ax = f.get_variation_axes()[0]
            f.set_variation_by_axes([max(ax["minimum"], min(ax["maximum"], WEIGHT_NUM.get(weight, 700)))])
        except Exception:
            pass
        return f
    return ImageFont.truetype(_font_file(weight, style.font), int(size), layout_engine=LAYOUT)


font.cache_clear = _font.cache_clear


# ------------------------------------------------------------------ compositing
_LUTS = {}


def _lut(a):
    a = int(clamp(a) * 255)
    if a not in _LUTS:
        _LUTS[a] = [v * a // 255 for v in range(256)]
    return _LUTS[a]


def with_alpha(spr, alpha):
    if alpha >= 0.997:
        return spr
    s = spr.copy()
    s.putalpha(spr.getchannel("A").point(_lut(alpha)))
    return s


def blit(dst, spr, x, y, alpha=1.0):
    """Композиция с обрезкой по краям и прозрачностью. (x, y) — левый верхний угол."""
    if alpha <= 0.004 or spr is None:
        return
    x, y = int(round(x)), int(round(y))
    W, H = dst.size
    w, h = spr.size
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    src = spr
    if (x0, y0, x1, y1) != (x, y, x + w, y + h):
        src = spr.crop((x0 - x, y0 - y, x1 - x, y1 - y))
    dst.alpha_composite(with_alpha(src, alpha), (x0, y0))


def blitc(dst, spr, cx, cy, alpha=1.0, scale=1.0, rot=0.0):
    """Композиция по центру, с масштабом/поворотом."""
    if spr is None or alpha <= 0.004 or scale <= 0.01:
        return
    if abs(scale - 1) > 0.004:
        spr = spr.resize((max(1, int(spr.width * scale)), max(1, int(spr.height * scale))), Image.BILINEAR)
    if abs(rot) > 0.05:
        spr = spr.rotate(rot, resample=Image.BILINEAR, expand=True)
    blit(dst, spr, cx - spr.width / 2, cy - spr.height / 2, alpha)


def glowify(base, color, radius, strength=1.0, mask=None, style=None):
    """Спрайт + цветное свечение по его альфе. Рисуется один раз."""
    pad = int(radius * 2.5)
    W, H = base.width + 2 * pad, base.height + 2 * pad
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    a = Image.new("L", (W, H), 0)
    a.paste(mask if mask is not None else base.getchannel("A"), (pad, pad))
    for r, s in ((radius, 0.9 * strength), (radius * 0.35, 0.6 * strength)):
        g = a.filter(ImageFilter.GaussianBlur(r)).point(lambda v, s=s: min(255, int(v * s)))
        layer = Image.new("RGBA", (W, H), col(color, style=style))
        layer.putalpha(g)
        out.alpha_composite(layer)
    out.alpha_composite(base, (pad, pad))
    return out


# ------------------------------------------------------------------ text
# `*` по краям слова, пунктуация снаружи звёздочек остаётся в слове: '(*word*),' -> '(word),'
_RUN_TOK = re.compile(r"([^\w*]*)(\**)(.*?)(\**)([^\w*]*)", re.S)


def _runs(text):
    """'Твоё *время*, да' -> [('Твоё', False), ('время,', True), ('да', False)] по словам."""
    out, acc = [], False
    for tok in text.split():
        lead, opens, core, closes, trail = _RUN_TOK.fullmatch(tok).groups()
        if opens:
            acc = True
        out.append((lead + core + trail, acc))
        if closes:
            acc = False
    return out


def wrap_runs(runs, f, maxw):
    lines, cur = [], []
    sp = f.getlength(" ")
    for w in runs:
        trial = cur + [w]
        width = sum(f.getlength(x[0]) for x in trial) + sp * (len(trial) - 1)
        if cur and maxw and width > maxw:
            lines.append(cur); cur = [w]
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def text_sprite(text, size, weight="bold", color="text", accent="accent", glow=0, glow_color=None,
                maxw=0, align="center", spacing=1.12, family=None, tracking=0.0, style=None):
    return _text_sprite(text, size, weight, color, accent, glow, glow_color, maxw, align, spacing, family, tracking,
                        _st(style))


@functools.lru_cache(maxsize=512)
def _text_sprite(text, size, weight, color, accent, glow, glow_color, maxw, align, spacing, family, tracking, style):
    f = font(size, weight, family, style)
    if tracking:
        return _tracked_sprite(text, f, size, color, tracking, style)
    lines = wrap_runs(_runs(text), f, maxw)
    asc, desc = f.getmetrics()
    lh = int(size * spacing)
    sp = f.getlength(" ")
    widths = [sum(f.getlength(w) for w, _ in L) + sp * (len(L) - 1) for L in lines]
    W = int(max(widths) + size * 0.3)
    H = int(lh * (len(lines) - 1) + asc + desc + size * 0.15)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, L in enumerate(lines):
        x = {"center": (W - widths[i]) / 2, "left": size * 0.15, "right": W - widths[i] - size * 0.15}[align]
        y = i * lh
        for w, hl in L:
            d.text((x, y), w, font=f, fill=style.col(accent if hl else color))
            x += f.getlength(w) + sp
    if glow:
        img = glowify(img, glow_color or accent, glow, 0.85, style=style)
    return img


text_sprite.cache_clear = _text_sprite.cache_clear


def _tracked_sprite(text, f, size, color, tracking, style=None):
    """Одна строка с трекингом (доля кегля между буквами) — капс-заголовки и ярлыки."""
    gap = size * tracking
    adv = [f.getlength(c) for c in text]
    W = int(sum(adv) + gap * max(0, len(text) - 1) + size * 0.3)
    asc, desc = f.getmetrics()
    img = Image.new("RGBA", (max(1, W), asc + desc + int(size * 0.15)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = size * 0.15
    for c, a in zip(text, adv):
        d.text((x, 0), c, font=f, fill=col(color, style=style))
        x += a + gap
    return img


# ------------------------------------------------------------------ shapes
def rrect(size, r, fill, outline=None, width=0):
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), r, fill=fill,
                                          outline=outline, width=width)
    return img


@functools.lru_cache(maxsize=64)
def rr_mask(w, h, r):
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), r, fill=255)
    return m


def radial(size, color, alpha=1.0, sharp=2.2, style=None):
    """Мягкое световое пятно."""
    return _radial(size, color, alpha, sharp, _st(style))


@functools.lru_cache(maxsize=64)
def _radial(size, color, alpha, sharp, style):
    n = size
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    r = np.sqrt((xx - n / 2) ** 2 + (yy - n / 2) ** 2) / (n / 2)
    a = np.clip(1 - r, 0, 1) ** sharp * 255 * alpha
    img = Image.new("RGBA", (n, n), style.col(color))
    img.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
    return img


def panel(w, h, r, border="accent", fill=None, glow=14, bw=3, fill_alpha=230, style=None):
    """Тёмная карточка с неоновой рамкой."""
    style = _st(style)
    fill = fill or style.pal["panel"]
    base = rrect((w, h), r, style.col(fill, fill_alpha), outline=style.col(border, 255), width=bw)
    ring = Image.new("L", (w, h), 0)
    ImageDraw.Draw(ring).rounded_rectangle((0, 0, w - 1, h - 1), r, outline=255, width=bw + 2)
    return glowify(base, border, glow, 0.9, mask=ring, style=style) if glow else base


# ------------------------------------------------------------------ background
class Background:
    """Градиент + зерно (статично) + плавающие световые пятна (функция глобального времени)."""

    def __init__(self, W, H, seed=7, style=None):
        self.W, self.H = W, H
        style = _st(style)
        y = np.linspace(0, 1, H, dtype=np.float32)[:, None]
        top, bot = np.array(style.pal["bg_top"], np.float32), np.array(style.pal["bg_bot"], np.float32)
        g = top + (bot - top) * y
        g = np.repeat(g[:, None, :], W, axis=1).reshape(H, W, 3)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        v = np.sqrt(((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2)
        g *= (1 - 0.55 * np.clip(v * 1.25, 0, 1) ** 2)[..., None]
        rng = np.random.default_rng(seed)
        g += rng.normal(0, 1.6, (H, W, 1)).astype(np.float32)  # зерно против бандинга
        self.base = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        m = min(W, H)
        rnd = random.Random(seed)
        self.speed = style.motion.get("bg", 1.0)  # бренд-кит motion.bg: живее (2–3) или спокойнее пятна
        self.blobs = []
        for c in ("violet", "magenta", "cyan", "violet"):
            s = int(m * rnd.uniform(0.75, 1.1))
            self.blobs.append({"spr": radial(s, c, 0.22, style=style), "x": rnd.uniform(0.1, 0.9), "y": rnd.uniform(0.1, 0.9),
                               "ax": rnd.uniform(0.08, 0.16), "ay": rnd.uniform(0.05, 0.12),
                               "wx": rnd.uniform(0.05, 0.11), "wy": rnd.uniform(0.04, 0.09),
                               "p": rnd.uniform(0, 6.28)})

    def frame(self, T, energy=1.0):
        img = self.base.copy()
        T *= self.speed
        for b in self.blobs:
            cx = (b["x"] + b["ax"] * math.sin(b["wx"] * T * 6.283 + b["p"])) * self.W
            cy = (b["y"] + b["ay"] * math.cos(b["wy"] * T * 6.283 + b["p"] * 1.3)) * self.H
            blit(img, b["spr"], cx - b["spr"].width / 2, cy - b["spr"].height / 2, energy)
        return img


class SolidBackground:
    """Сплошной фон бренд-кита (`background: solid`): цвет bg, без пятен."""

    def __init__(self, W, H, style=None):
        pal = _st(style).pal
        self.base = Image.new("RGBA", (W, H), tuple(pal.get("bg", pal["bg_top"])) + (255,))

    def frame(self, T, energy=1.0):
        return self.base.copy()


class PhotoBackground:
    """Фото-подложка бренд-кита (`background: {type: image, file, dim}`): кадрирование по центру «cover»,
    затемнение к цвету bg на долю dim — текст поверх читается."""

    def __init__(self, W, H, file, dim=0.45, style=None):
        pal = _st(style).pal
        src = Image.open(file).convert("RGB")
        k = max(W / src.width, H / src.height)
        src = src.resize((max(W, round(src.width * k)), max(H, round(src.height * k))), Image.LANCZOS)
        x, y = (src.width - W) // 2, (src.height - H) // 2
        src = src.crop((x, y, x + W, y + H))
        tint = Image.new("RGB", (W, H), tuple(pal.get("bg", pal["bg_top"])))
        self.base = Image.blend(src, tint, float(dim)).convert("RGBA")

    def frame(self, T, energy=1.0):
        return self.base.copy()


# ------------------------------------------------------------------ icons
def _ic_clock(d, s, c, w):
    d.ellipse((w, w, s - w, s - w), outline=c, width=w)
    m = s / 2
    d.line((m, m, m, s * 0.22), fill=c, width=w); d.line((m, m, s * 0.70, m + s * 0.08), fill=c, width=w)
    d.ellipse((m - w, m - w, m + w, m + w), fill=c)


def _ic_laugh(d, s, c, w):
    d.ellipse((w, w, s - w, s - w), outline=c, width=w)
    for x in (0.36, 0.64):
        d.arc((s * (x - 0.09), s * 0.32, s * (x + 0.09), s * 0.46), 200, 340, fill=c, width=w)
    d.chord((s * 0.27, s * 0.48, s * 0.73, s * 0.80), 0, 180, fill=c)


def _ic_book(d, s, c, w):
    d.polygon([(s * .5, s * .28), (s * .1, s * .2), (s * .1, s * .8), (s * .5, s * .88)], outline=c, width=w)
    d.polygon([(s * .5, s * .28), (s * .9, s * .2), (s * .9, s * .8), (s * .5, s * .88)], outline=c, width=w)
    for k in (0.42, 0.55):
        d.line((s * .18, s * k, s * .42, s * (k + .04)), fill=c, width=max(2, w // 2))
        d.line((s * .58, s * (k + .04), s * .82, s * k), fill=c, width=max(2, w // 2))


def _ic_news(d, s, c, w):
    d.rounded_rectangle((s * .12, s * .18, s * .88, s * .82), s * .06, outline=c, width=w)
    d.rectangle((s * .22, s * .28, s * .48, s * .5), fill=c)
    for k in (0.3, 0.42):
        d.line((s * .56, s * k, s * .78, s * k), fill=c, width=max(2, w // 2))
    for k in (0.6, 0.71):
        d.line((s * .22, s * k, s * .78, s * k), fill=c, width=max(2, w // 2))


def _ic_question(d, s, c, w):
    d.ellipse((w, w, s - w, s - w), outline=c, width=w)
    d.arc((s * .33, s * .2, s * .67, s * .52), 180, 405, fill=c, width=w)
    d.line((s * .5, s * .5, s * .5, s * .62), fill=c, width=w)
    d.ellipse((s * .5 - w, s * .72 - w, s * .5 + w, s * .72 + w), fill=c)


def _ic_bell(d, s, c, w):
    d.chord((s * .2, s * .15, s * .8, s * .95), 180, 360, outline=c, width=w)
    d.line((s * .2, s * .55, s * .2, s * .7), fill=c, width=w); d.line((s * .8, s * .55, s * .8, s * .7), fill=c, width=w)
    d.line((s * .12, s * .72, s * .88, s * .72), fill=c, width=w)
    d.ellipse((s * .42, s * .76, s * .58, s * .9), fill=c)


def _ic_heart(d, s, c, w):
    d.ellipse((s * .12, s * .2, s * .52, s * .58), fill=c); d.ellipse((s * .48, s * .2, s * .88, s * .58), fill=c)
    d.polygon([(s * .14, s * .46), (s * .86, s * .46), (s * .5, s * .86)], fill=c)


def _ic_play(d, s, c, w):
    d.rounded_rectangle((w, s * .15, s - w, s * .85), s * .14, outline=c, width=w)
    d.polygon([(s * .42, s * .34), (s * .42, s * .66), (s * .68, s * .5)], fill=c)


def _ic_check(d, s, c, w):
    d.ellipse((w, w, s - w, s - w), outline=c, width=w)
    d.line((s * .3, s * .52, s * .45, s * .67, s * .72, s * .36), fill=c, width=int(w * 1.3), joint="curve")


def _ic_bolt(d, s, c, w):
    d.polygon([(s * .58, s * .08), (s * .22, s * .56), (s * .48, s * .56), (s * .4, s * .92),
               (s * .78, s * .42), (s * .52, s * .42)], fill=c)


def _ic_eye(d, s, c, w):
    d.chord((s * .06, s * .2, s * .94, s * .8), 200, 340, outline=c, width=w)
    d.chord((s * .06, s * .2, s * .94, s * .8), 20, 160, outline=c, width=w)
    d.ellipse((s * .38, s * .38, s * .62, s * .62), fill=c)


def _ic_chart(d, s, c, w):
    for i, h in enumerate((0.35, 0.55, 0.45, 0.75)):
        x = s * (0.16 + i * 0.19)
        d.rounded_rectangle((x, s * (0.85 - h), x + s * 0.13, s * 0.85), s * 0.03, fill=c)


def _ic_star(d, s, c, w):
    pts = []
    for i in range(10):
        r = s * (0.44 if i % 2 == 0 else 0.19)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a)))
    d.polygon(pts, fill=c)


def _ic_phone(d, s, c, w):
    d.rounded_rectangle((s * .28, s * .06, s * .72, s * .94), s * .08, outline=c, width=w)
    d.line((s * .43, s * .84, s * .57, s * .84), fill=c, width=w)


def _ic_hourglass(d, s, c, w):
    d.line((s * .22, s * .1, s * .78, s * .1), fill=c, width=w); d.line((s * .22, s * .9, s * .78, s * .9), fill=c, width=w)
    d.line((s * .28, s * .1, s * .72, s * .9), fill=c, width=w); d.line((s * .72, s * .1, s * .28, s * .9), fill=c, width=w)
    d.polygon([(s * .38, s * .82), (s * .62, s * .82), (s * .5, s * .62)], fill=c)


def _ic_target(d, s, c, w):
    for k in (0.08, 0.24, 0.40):
        d.ellipse((s * k, s * k, s * (1 - k), s * (1 - k)), outline=c, width=w)


def _ic_brain(d, s, c, w):
    d.ellipse((s * .12, s * .2, s * .56, s * .8), outline=c, width=w)
    d.ellipse((s * .44, s * .2, s * .88, s * .8), outline=c, width=w)
    d.arc((s * .25, s * .35, s * .45, s * .55), 270, 90, fill=c, width=max(2, w // 2))
    d.arc((s * .55, s * .45, s * .75, s * .65), 90, 270, fill=c, width=max(2, w // 2))


def _ic_lock(d, s, c, w):
    d.arc((s * .3, s * .1, s * .7, s * .55), 180, 360, fill=c, width=w)
    d.line((s * .3, s * .32, s * .3, s * .45), fill=c, width=w); d.line((s * .7, s * .32, s * .7, s * .45), fill=c, width=w)
    d.rounded_rectangle((s * .2, s * .44, s * .8, s * .9), s * .08, fill=c)


ICONS = {"clock": _ic_clock, "laugh": _ic_laugh, "book": _ic_book, "story": _ic_book, "news": _ic_news,
         "question": _ic_question, "bell": _ic_bell, "heart": _ic_heart, "play": _ic_play, "video": _ic_play,
         "check": _ic_check, "bolt": _ic_bolt, "eye": _ic_eye, "chart": _ic_chart, "star": _ic_star,
         "phone": _ic_phone, "hourglass": _ic_hourglass, "target": _ic_target, "brain": _ic_brain,
         "lock": _ic_lock}


def icon(name, size, color="accent", glow=True, style=None):
    return _icon(name, size, color, glow, _st(style))


@functools.lru_cache(maxsize=128)
def _icon(name, size, color, glow, style):
    ss = 3  # суперсэмплинг для гладких линий
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ICONS.get(name, _ic_star)(d, S, style.col(color), max(3, int(S * 0.07)))
    img = img.resize((size, size), Image.LANCZOS)
    return glowify(img, color, size * 0.12, 0.9, style=style) if glow else img


# ------------------------------------------------------------------ phone
class Phone:
    """Геометрия и корпус смартфона; одинаковы во всех сценах -> склейки незаметны."""

    GLOW_H, GLOW_W = 1.08, 0.55  # видимый корпус со свечением: высота и ширина в долях высоты экрана sh

    def __init__(self, W, H, style=None, box=None, top=0.0):
        """box — рамка (x0, y0, x1, y1) высокого кадра (ROADMAP B2.1): корпус со свечением вписан в неё ниже полосы
        высотой top (счётчик, ряд-история; её центр — strip_cy), стопка «полоса + телефон» по центру рамки."""
        self.W, self.H = W, H
        style = _st(style)
        if box is not None:
            bw_, bh_ = box[2] - box[0], box[3] - box[1]
            self.sh = int(min(H * 0.60, (bh_ - top) / self.GLOW_H, bw_ / self.GLOW_W))
        elif H >= W:
            self.sh = int(H * 0.60)
        else:
            self.sh = int(H * 0.74)
        self.sw = int(self.sh * 0.47)
        self.r = int(self.sw * 0.12)
        self.bez = max(10, int(self.sw * 0.035))
        self.cx, self.cy = W / 2, H * (0.44 if H >= W else 0.45)
        self.strip_cy = None
        if box is not None:
            body = self.sh * self.GLOW_H
            y0 = box[1] + (bh_ - top - body) / 2
            self.cx, self.cy, self.strip_cy = (box[0] + box[2]) / 2, y0 + top + body / 2, y0 + top / 2
        bw, bh = self.sw + 2 * self.bez, self.sh + 2 * self.bez
        body = rrect((bw, bh), self.r + self.bez, (10, 9, 20, 255), outline=style.col("violet", 255), width=3)
        ring = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(ring).rounded_rectangle((0, 0, bw - 1, bh - 1), self.r + self.bez, outline=255, width=5)
        self.body = glowify(body, "violet", int(self.sw * 0.05), 0.9, mask=ring, style=style)
        self.pad = (self.body.width - bw) // 2
        self.mask = rr_mask(self.sw, self.sh, self.r)
        nw, nh = int(self.sw * 0.3), int(self.sw * 0.075)
        self.notch = rrect((nw, nh), nh // 2, (4, 4, 8, 255))

    def screen(self):
        return Image.new("RGBA", (self.sw, self.sh), (12, 10, 26, 255))

    def draw(self, dst, scr, scale=1.0, dx=0.0, dy=0.0, alpha=1.0, body_alpha=None):
        s = Image.new("RGBA", self.body.size, (0, 0, 0, 0))
        s.alpha_composite(self.body)
        sc = scr.copy(); sc.putalpha(self.mask)
        s.alpha_composite(sc, (self.pad + self.bez, self.pad + self.bez))
        s.alpha_composite(self.notch, (s.width // 2 - self.notch.width // 2, self.pad + self.bez + int(self.sw * 0.03)))
        blitc(dst, s, self.cx + dx, self.cy + dy, alpha, scale)
