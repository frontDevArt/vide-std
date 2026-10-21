"""Пресет `lab` — визуальный язык канала Notes From The Mind (channel/STYLE.md, эталон channel/style-demo.html).

Что здесь:
- LabBackground — фон §4: две «дышащие» подсветки, лабораторная сетка, пылинки; функция ГЛОБАЛЬНОГО времени;
- apply_camera — дрейф камеры для слоя контента (фон — в 0,5×, параллакс);
- фирменные элементы §8: штамп вердикта, карточка исследования, «Миф → Реальность», толпа = выборке,
  карточка главы, часы дня, «Нейрон»;
- шаблоны композиции §5: lab_hero_stack, lab_flow, lab_versus, lab_crowd, lab_diagram, lab_full_number
  (+ lab_chapter, lab_verdict).

Синхронизация: у каждого элемента параметр `at` — слово-триггер ("66", "w:median", "verdict#2"),
номер бита (int) или секунды ("1.5s"). Старт — за 4 кадра до слова (STYLE §11).
Морфинг через склейку — только через state (`lab_chrome`, `lab_hero`, `lab_clock`), как требует SCENE_SPEC.
Координаты — в «дизайн-пикселях» 1920×1080 (как в STYLE), масштаб self.z = W / 1920.
"""
from __future__ import annotations

import functools
import math
import random
import re

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import gfx as G
from . import motion as M
from .templates import Template, template

VERDICTS = {"TRUE": "true", "HALF-TRUE": "half", "MYTH": "myth", "NO EVIDENCE": "noev"}
SS = 3  # суперсэмплинг для векторных фигур


def C(name, a=255):
    return G.col(name, a)


# ===================================================================== background §4
class LabBackground:
    """Сплошной bg + подсветки (циан сверху-слева, лаванда снизу-справа, дыхание ±4 % за 7 с),
    сетка 48 px в нижних 40 % с затуханием вверх, 34 пылинки 1–2 px плывут вверх 8–20 px/с."""

    def __init__(self, W, H, seed=7):
        self.W, self.H = W, H
        self.z = W / 1920 if W >= H else H / 1920
        self.lw, self.lh = max(2, W // 4), max(2, H // 4)
        ys, xs = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        self.xs, self.ys = (xs + 0.5) * W / self.lw, (ys + 0.5) * H / self.lh
        self.base = np.array(G.PAL["bg"], np.float32)
        self.c1 = np.array(G.PAL["accent"], np.float32)
        self.c2 = np.array(G.PAL["accent2"], np.float32)
        rng = np.random.default_rng(seed)
        g = np.clip(rng.normal(1.2, 0.9, (H, W)), 0, 3).astype(np.uint8)  # зерно против бандинга
        self.grain = Image.merge("RGB", [Image.fromarray(g, "L")] * 3)
        # сетка: шире кадра на 2 клетки, чтобы сдвигать (параллакс)
        cell = max(8, int(round(48 * self.z)))
        self.cell = cell
        top = int(H * 0.593)
        gw = W + 2 * cell
        grid = Image.new("RGBA", (gw, H - top), (255, 255, 255, 0))  # белые линии, видимость — альфой
        a = np.zeros((H - top, gw), np.float32)
        ramp = (np.arange(H - top, dtype=np.float32) / max(1, H - top - 1))[:, None]
        a[:, ::cell] = 1.0
        a[::cell, :] = 1.0
        a = (a * ramp * 0.065 * 255).astype(np.uint8)
        grid.putalpha(Image.fromarray(a, "L"))
        self.grid, self.gtop = grid, top
        rnd = random.Random(seed)
        self.dust = [(rnd.random() * W, rnd.random() * H, (8 + rnd.random() * 12) * self.z,
                      (0.8 + rnd.random() * 1.4) * self.z, 0.18 + rnd.random() * 0.22) for _ in range(34)]

    def _glow(self, cx, cy, r, alpha):
        d = np.sqrt((self.xs - cx) ** 2 + (self.ys - cy) ** 2) / r
        return np.clip(1 - d, 0, 1) * alpha

    def frame(self, T):
        W, H, z = self.W, self.H, self.z
        _, dx, dy = M.camera(T)
        cx, cy = dx * 0.5 * z, dy * 0.5 * z  # фон — в 0,5× от контента
        br = 1 + 0.04 * math.sin(T * math.tau / 7)
        a1 = self._glow(380 * z + cx + 30 * z * math.sin(T / 3), 180 * z + cy, 950 * z, 0.17 * br)
        a2 = self._glow(W - 300 * z + cx, H - 140 * z + cy + 20 * z * math.cos(T / 4), 900 * z, 0.15 * (2 - br))
        img = self.base * (1 - a1[..., None]) + self.c1 * a1[..., None]
        img = img * (1 - a2[..., None]) + self.c2 * a2[..., None]
        low = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
        out = ImageChops.add(low.resize((W, H), Image.BILINEAR), self.grain).convert("RGBA")
        off = int(round(cx)) % self.cell
        out.alpha_composite(self.grid.crop((self.cell - off, 0, self.cell - off + W, self.grid.height)), (0, self.gtop))
        d = ImageDraw.Draw(out, "RGBA")
        for x, y, v, r, a in self.dust:
            yy = (y - T * v) % H
            xx = x + cx
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(214, 236, 255, int(a * 255)))
        return out


def apply_camera(layer, T):
    """Масштаб/сдвиг слоя контента вокруг центра кадра (motion.camera — от глобального времени)."""
    s, dx, dy = M.camera(T)
    W, H = layer.size
    z = W / 1920 if W >= H else H / 1920
    cx, cy = W / 2, H / 2
    a = 1 / s
    return layer.transform((W, H), Image.AFFINE, (a, 0, cx - (cx + dx * z) * a, 0, a, cy - (cy + dy * z) * a),
                           resample=Image.BILINEAR)


# ===================================================================== drawing primitives
def _ss_canvas(w, h):
    img = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _down(img, w, h):
    return img.resize((int(round(w)), int(round(h))), Image.LANCZOS)


@functools.lru_cache(maxsize=256)
def glass(w, h, r):
    """Карточка-стекло §5: заливка bg2 72 %, рамка 1 px line (10 %), верхний блик 1 px белым 6 %."""
    img, d = _ss_canvas(w, h)
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, fill=C("bg2", 184), outline=(255, 255, 255, 26), width=SS)
    d.line((r * SS, SS * 1.5, (w - r) * SS, SS * 1.5), fill=(255, 255, 255, 18), width=SS)
    return _down(img, w, h)


@functools.lru_cache(maxsize=256)
def focus_ring(w, h, r, color="accent"):
    """Активный элемент: рамка accent 1,5 px + внешнее свечение 24 px при 35 %. Рисуется поверх карточки."""
    img, d = _ss_canvas(w, h)
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), r * SS, outline=C(color), width=int(1.5 * SS))
    ring = _down(img, w, h)
    return G.glowify(ring, color, 12, 0.55)


def ring_pad(w, h, r, color="accent"):
    spr = focus_ring(w, h, r, color)
    return spr, (spr.width - w) // 2


@functools.lru_cache(maxsize=512)
def txt(text, size, weight="extrabold", color="text", family="head", tracking=0.0):
    return G.text_sprite(text, int(size), weight, color, family=family, tracking=tracking, align="left")


def rich(text, size, maxw, color="text", hl="accent2", weight="extrabold", lh=1.15):
    """Текст с выделением *слов*: лавандовая полоса в нижних 38 % строки (как в демо)."""
    f = G.font(int(size), weight, "head")
    lines = G.wrap_runs(G._runs(text), f, maxw)
    sp = f.getlength(" ")
    L = int(size * lh)
    asc, desc = f.getmetrics()
    W = int(max(sum(f.getlength(w) for w, _ in ln) + sp * (len(ln) - 1) for ln in lines) + size * 0.2)
    H = L * (len(lines) - 1) + asc + desc
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    for i, ln in enumerate(lines):
        x, y = 0.0, i * L
        for w, h in ln:
            ww = f.getlength(w)
            if h:
                d.rectangle((x - 2, y + asc * 0.62, x + ww + 2, y + asc + desc * 0.35), fill=C(hl, 90))
            x += ww + sp
        x = 0.0
        for w, h in ln:
            d.text((x, y), w, font=f, fill=C(color))
            x += f.getlength(w) + sp
    return img


# --- line icons §9: 2 px, скруглённые концы, в плитке 72×72
def _li(name, d, s, c, w):
    m = s * 0.18
    if name == "book":
        d.line((m, m, m, s - m), fill=c, width=w)
        d.rounded_rectangle((m, m, s - m, s - m * 1.4), s * 0.06, outline=c, width=w)
        d.line((s * .42, s * .36, s * .64, s * .36), fill=c, width=w)
    elif name == "chat":
        d.rounded_rectangle((m, m, s - m, s * .7), s * .14, outline=c, width=w)
        d.line((s * .3, s * .7, s * .22, s * .86), fill=c, width=w); d.line((s * .22, s * .86, s * .44, s * .7), fill=c, width=w)
    elif name == "flask":
        d.line((s * .38, m, s * .62, m), fill=c, width=w)
        d.line((s * .42, m, s * .42, s * .42), fill=c, width=w); d.line((s * .58, m, s * .58, s * .42), fill=c, width=w)
        d.line((s * .42, s * .42, s * .2, s * .8), fill=c, width=w); d.line((s * .58, s * .42, s * .8, s * .8), fill=c, width=w)
        d.line((s * .2, s * .8, s * .8, s * .8), fill=c, width=w)
    elif name == "person":
        d.ellipse((s * .36, m, s * .64, s * .46), outline=c, width=w)
        d.arc((s * .2, s * .52, s * .8, s * 1.1), 180, 360, fill=c, width=w)
    elif name == "people":
        for ox in (-.14, .14):
            d.ellipse((s * (.38 + ox), s * .2, s * (.62 + ox), s * .46), outline=c, width=w)
            d.arc((s * (.24 + ox), s * .54, s * (.76 + ox), s * 1.0), 180, 360, fill=c, width=w)
    elif name == "alarm" or name == "clock":
        d.ellipse((m, m * 1.2, s - m, s - m * 0.8), outline=c, width=w)
        d.line((s / 2, s * .34, s / 2, s * .54), fill=c, width=w); d.line((s / 2, s * .54, s * .64, s * .62), fill=c, width=w)
    elif name == "phone":
        d.rounded_rectangle((s * .3, m, s * .7, s - m), s * .08, outline=c, width=w)
        d.line((s * .45, s * .74, s * .55, s * .74), fill=c, width=w)
    elif name == "tag" or name == "money":
        d.polygon([(s * .2, s * .2), (s * .55, s * .2), (s * .82, s * .5), (s * .5, s * .82), (s * .2, s * .52)], outline=c, width=w)
        d.ellipse((s * .3, s * .3, s * .4, s * .4), outline=c, width=w)
    elif name == "mirror":
        d.ellipse((s * .26, m, s * .74, s * .7), outline=c, width=w); d.line((s / 2, s * .7, s / 2, s - m), fill=c, width=w)
    elif name == "moon":
        d.arc((m, m, s - m, s - m), 60, 300, fill=c, width=w); d.arc((s * .38, m, s * .98, s - m), 120, 240, fill=c, width=w)
    elif name == "chart":
        d.line((m, s - m, s - m, s - m), fill=c, width=w)
        for i, hgt in enumerate((.4, .62, .3, .8)):
            x = m + (i + .5) * (s - 2 * m) / 4
            d.line((x, s - m, x, s - m - hgt * (s - 2 * m)), fill=c, width=w)
    elif name == "check":
        d.line((s * .22, s * .52, s * .42, s * .72), fill=c, width=w); d.line((s * .42, s * .72, s * .8, s * .3), fill=c, width=w)
    elif name == "cross":
        d.line((s * .26, s * .26, s * .74, s * .74), fill=c, width=w); d.line((s * .74, s * .26, s * .26, s * .74), fill=c, width=w)
    elif name == "question":
        d.arc((s * .3, s * .14, s * .7, s * .52), 200, 90, fill=c, width=w)
        d.line((s / 2, s * .52, s / 2, s * .64), fill=c, width=w); d.ellipse((s * .47, s * .76, s * .53, s * .82), fill=c)
    else:
        return False
    return True


@functools.lru_cache(maxsize=128)
def line_icon(name, size, color="accent"):
    S = int(size * SS)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if not _li(name, d, S, C(color), max(2, int(2 * SS * size / 38))):
        return G.icon(name, size, color, glow=False)
    return img.resize((size, size), Image.LANCZOS)


@functools.lru_cache(maxsize=64)
def tile(icon_name, size=72, color="accent"):
    img, d = _ss_canvas(size, size)
    d.rounded_rectangle((0, 0, size * SS - 1, size * SS - 1), 14 * SS, fill=C("bg2"), outline=(255, 255, 255, 26), width=SS)
    t = _down(img, size, size)
    ic = line_icon(icon_name, int(size * 0.53), color)
    t.alpha_composite(ic, ((size - ic.width) // 2, (size - ic.height) // 2))
    return t


@functools.lru_cache(maxsize=8)
def person_icon(w, h, color="text"):
    img, d = _ss_canvas(w, h)
    k = SS * w / 30
    d.ellipse((7.5 * k, 1.5 * k, 22.5 * k, 16.5 * k), fill=C(color))
    d.rounded_rectangle((2 * k, 18 * k, 28 * k, 36 * k + 30), 13 * k, fill=C(color))
    return _down(img, w, h)


def blurred(spr, level, _cache={}):
    """Размытие 8→0 при появлении: 3 заранее размытые копии вместо размытия на каждый кадр."""
    if level < 1.2:
        return spr
    lv = 2.5 if level < 3.8 else 5 if level < 6.5 else 8
    key = (id(spr), lv)
    if len(_cache) > 600:  # счётчики дают много разных спрайтов
        _cache.clear()
    if key not in _cache:
        pad = int(lv * 2)
        big = Image.new("RGBA", (spr.width + 2 * pad, spr.height + 2 * pad), (0, 0, 0, 0))
        big.alpha_composite(spr, (pad, pad))
        _cache[key] = (big.filter(ImageFilter.GaussianBlur(lv)), pad, spr)
    return _cache[key]


def put(img, spr, x, y, alpha=1.0, scale=1.0, blur=0.0, rot=0.0, anchor="lt"):
    """Положить спрайт: (x, y) — левый верхний угол (anchor lt) или центр (c). Масштаб — от центра."""
    if spr is None or alpha <= 0.004:
        return
    if anchor == "lt":
        cx, cy = x + spr.width / 2, y + spr.height / 2
    else:
        cx, cy = x, y
    b = blurred(spr, blur)
    if isinstance(b, tuple):
        spr = b[0]
    G.blitc(img, spr, cx, cy, alpha, scale, rot)


# ===================================================================== brand elements §8
@functools.lru_cache(maxsize=8)
def dot_glow(d):
    """Светящаяся точка акцента (пилюля рубрики, активный шаг)."""
    return G.glowify(G.rrect((int(d), int(d)), int(d / 2), C("accent")), "accent", d * 0.6, 0.9)


@functools.lru_cache(maxsize=16)
def stamp_sprite(verdict, z=1.0):
    """Штамп вердикта: скруглённая плашка, обводка цвета вердикта, капс Unbounded, «чернильная» текстура."""
    c = VERDICTS.get(verdict.upper(), "myth")
    word = txt(verdict.upper(), 170 * z, "extrabold", c, "num", 0.04)
    pw, ph = word.width + int(112 * z), word.height + int(36 * z)
    rings = int(13 * z)
    W, H = pw + 2 * rings, ph + 2 * rings
    img, d = _ss_canvas(W, H)
    d.rounded_rectangle((0, 0, W * SS - 1, H * SS - 1), (26 + 13) * z * SS, outline=C(c, 115), width=int(3 * z * SS))
    d.rounded_rectangle((3 * z * SS, 3 * z * SS, (W - 3 * z) * SS, (H - 3 * z) * SS), (26 + 10) * z * SS, fill=(10, 13, 20, 219))
    d.rounded_rectangle((rings * SS, rings * SS, (W - rings) * SS, (H - rings) * SS), 26 * z * SS, outline=C(c), width=int(7 * z * SS))
    box = _down(img, W, H)
    box.alpha_composite(word, ((W - word.width) // 2, (H - word.height) // 2 + int(2 * z)))
    # чернильная текстура: случайные «выщербины» в альфе
    rng = np.random.default_rng(len(verdict))
    a = np.array(box.getchannel("A"), np.float32)
    noise = rng.random(a.shape).astype(np.float32)
    noise = np.array(Image.fromarray((noise * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    a *= np.clip(0.78 + noise * 0.5, 0, 1)
    box.putalpha(Image.fromarray(a.astype(np.uint8)))
    return G.glowify(box, c, 40 * z, 0.45)


@functools.lru_cache(maxsize=8)
def study_card(authors, where, evidence, z=1.0, w=724):
    """Карточка исследования: STUDY · сила доказательств (5 сегментов) · авторы · журнал, год, n."""
    w = int(w * z)
    tag = txt("STUDY", 19 * z, "medium", "bg", "mono", 0.06)
    who = G.text_sprite(authors, int(30 * z), "extrabold", "text", family="head", align="left", maxw=int(w - 56 * z))
    whr = txt(where, 19 * z, "medium", "dim", "mono")
    h = int(24 * z + tag.height + 14 * z + who.height + 6 * z + whr.height + 24 * z)
    card = glass(w, h, int(18 * z)).copy()
    d = ImageDraw.Draw(card, "RGBA")
    x0, y0 = int(28 * z), int(24 * z)
    d.rounded_rectangle((x0, y0, x0 + tag.width + 10 * z, y0 + tag.height + 4 * z), 8 * z, fill=C("accent"))
    card.alpha_composite(tag, (x0 + int(3 * z), y0 + int(2 * z)))
    lab = txt("EVIDENCE", 16 * z, "medium", "dim", "mono")
    mx = int(w - 28 * z - 5 * 36 * z)
    card.alpha_composite(lab, (mx - lab.width - int(6 * z), y0 + int(4 * z)))
    for i in range(5):
        x = mx + i * 36 * z
        on = i < int(evidence)
        d.rounded_rectangle((x, y0 + 9 * z, x + 30 * z, y0 + 19 * z), 3 * z, fill=C("accent") if on else (255, 255, 255, 31))
    y = y0 + tag.height + int(18 * z)
    card.alpha_composite(who, (x0 - int(4 * z), y))
    card.alpha_composite(whr, (x0 - int(3 * z), y + who.height + int(6 * z)))
    return card


@functools.lru_cache(maxsize=8)
def neuron_sprite(mood="neutral", blink=False, z=1.0):
    """«Нейрон»: круглая клетка, два глаза, три отростка. mood: neutral | surprised | nod | facepalm."""
    S = 170
    img, d = _ss_canvas(S * z, S * z)
    k = SS * z
    ac = C("accent")
    for (x1, y1, x2, y2) in ((85, 40, 85, 12), (48, 58, 24, 38), (122, 58, 146, 38)):
        d.line((x1 * k, y1 * k, x2 * k, y2 * k), fill=G.col("accent", 230), width=int(5 * k))
        d.ellipse(((x2 - 5) * k, (y2 - 5) * k, (x2 + 5) * k, (y2 + 5) * k), fill=ac)
    d.ellipse((27 * k, 42 * k, 143 * k, 158 * k), fill=C("ink"), outline=ac, width=int(4 * k))
    if blink or mood == "facepalm":
        for ex in (64, 106):
            d.line(((ex - 12) * k, 98 * k, (ex + 12) * k, 98 * k), fill=C("text"), width=int(4 * k))
    else:
        pr = 4 if mood == "surprised" else 7
        for ex in (64, 106):
            d.ellipse(((ex - 15) * k, 81 * k, (ex + 15) * k, 111 * k), fill=C("text"))
            d.ellipse(((ex - pr) * k, (96 - pr) * k, (ex + pr) * k, (96 + pr) * k), fill=C("bg"))
    if mood == "surprised":
        d.ellipse((77 * k, 120 * k, 93 * k, 140 * k), fill=C("bg"))
    elif mood == "facepalm":
        d.arc((70 * k, 128 * k, 100 * k, 142 * k), 200, 340, fill=C("bg"), width=int(4 * k))
        d.rounded_rectangle((20 * k, 70 * k, 70 * k, 108 * k), 16 * k, fill=C("accent2"))  # «ладонь»-отросток
    else:
        d.ellipse((73 * k, 125 * k, 97 * k, 135 * k), fill=C("bg"))
    return _down(img, S * z, S * z)


@functools.lru_cache(maxsize=16)
def clock_face(z=1.0):
    S = int(84 * z)
    img, d = _ss_canvas(S, S)
    d.ellipse((SS, SS, S * SS - SS, S * SS - SS), fill=C("bg2", 200), outline=C("accent"), width=int(2.5 * z * SS))
    for i in range(12):
        a = i / 12 * math.tau
        r1, r2 = S * SS * 0.40, S * SS * (0.34 if i % 3 == 0 else 0.37)
        c = S * SS / 2
        d.line((c + r1 * math.sin(a), c - r1 * math.cos(a), c + r2 * math.sin(a), c - r2 * math.cos(a)),
               fill=C("dim"), width=int(2 * z * SS))
    return _down(img, S, S)


def _minutes(hhmm):
    m = re.match(r"(\d{1,2}):(\d{2})", str(hhmm or ""))
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


# ===================================================================== base template
class LabTemplate(Template):
    """База шаблонов lab: триггеры по словам, шапка (рубрика + шаги / часы), фокус, уход, вердикт,
    «Нейрон», источник, перенос героя-числа через склейку (state)."""
    camera = True
    COMMON = {"chrome": None, "keep": [], "source": None, "verdict": None, "neuron": None}

    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        self.z = self.W / 1920 if self.W >= self.H else self.W / 1080
        self.words = scene.get("words") or []
        self._planned = False

    # ---------- триггеры
    def _norm(self, w):
        return re.sub(r"[^\w]+", "", str(w).lower().replace("’", "'"))

    def at(self, spec, default=None, lead=True):
        """'66' | 'w:median' | 'word#2' | 'median of' (последовательность) | 3 (бит) | '1.5s' | 2.4 (сек)."""
        if spec is None:
            return default
        if isinstance(spec, bool):
            return default
        if isinstance(spec, int):
            t = self.bt(spec, default)
            return max(0.0, t - M.fr(M.F_LEAD)) if lead and t is not None else t
        if isinstance(spec, float):
            return spec
        s = str(spec).strip()
        m = re.fullmatch(r"([\d.]+)s", s)
        if m:
            return float(m.group(1))
        s = s[2:] if s.startswith("w:") else s
        occ = 1
        if "#" in s:
            s, o = s.rsplit("#", 1)
            occ = int(o or 1)
        seq = [self._norm(x) for x in s.split() if self._norm(x)]
        ws = [self._norm(w["w"]) for w in self.words]
        hit = 0
        for i in range(len(ws) - len(seq) + 1):
            if ws[i:i + len(seq)] == seq:
                hit += 1
                if hit == occ:
                    t = self.words[i]["t0"]
                    return max(0.0, t - M.fr(M.F_LEAD)) if lead else t
        print(f"  ⚠️  {self.s.get('chapter')}/{self.s.get('id')}: слово-триггер «{spec}» не найдено в озвучке")
        return default

    def seq_times(self, items, start, key="at"):
        """Времена появления группы: по триггерам, иначе стаггер от start."""
        out = []
        for i, it in enumerate(items):
            out.append(self.at((it or {}).get(key), M.stagger(i, start)))
        return out

    # ---------- план (без спрайтов: нужен и для state_out/sfx_events)
    def plan(self):
        if self._planned:
            return
        self._planned = True
        p = self.p
        prev = self.state.get("lab_chrome") or {}
        ch = dict(prev)
        ch.update(p.get("chrome") or {})
        self.chrome, self.chrome_prev = ch, prev
        self.keep = set(p.get("keep") or [])
        self.exit_t = self.D - M.fr(M.F_EXIT) - 0.06
        v = p.get("verdict")
        self.v_t = self.at(v.get("at"), self.D * 0.6) if v else None
        n = p.get("neuron")
        if n:
            self.n_t = self.at(n.get("at"), (self.v_t + 1.1) if self.v_t is not None else self.D * 0.7)
        else:
            self.n_t = None
        src = p.get("source")
        self.src_t = self.at(src.get("at"), 0.9) if src else None
        self.plan_body()

    def plan_body(self):
        pass

    def state_out(self):
        self.plan()
        out = {"lab_chrome": self.chrome}
        if self.chrome.get("clock"):
            out["lab_clock"] = self.chrome["clock"]
        h = self.hero_out()
        out["lab_hero"] = h if (h and "hero" in self.keep) else None
        return out

    def hero_out(self):
        return None

    # ---------- звук §10
    def sfx_events(self):
        """[(t_локальное, имя)] — попы на появления (один на группу), тики счётчиков, удар вердикта."""
        self.plan()
        ev = []
        if self.src_t is not None:
            ev.append((self.src_t, "pop"))
        if self.v_t is not None:
            ev += [(self.v_t - 0.55, "riser"), (self.v_t, "thud")]
        if self.n_t is not None:
            ev.append((self.n_t, "pop"))
        return ev + self.sfx_body()

    def sfx_body(self):
        return []

    @staticmethod
    def ticks(t0, dur):
        """Мягкие тики счётчика, учащающиеся к концу."""
        out, x, step = [], t0, 0.11
        while x < t0 + dur:
            out.append((x, "tick"))
            x += step
            step = max(0.05, step * 0.86)
        return out

    # ---------- общий setup
    def setup(self):
        self.plan()
        z = self.z
        ch = self.chrome
        self.pill = self._pill(ch.get("rubric"), ch.get("number")) if ch.get("rubric") else None
        self.steps = [s.upper() for s in ch.get("steps") or []]
        self.step_spr = [(txt(s, 20 * z, "medium", "dim", "mono", 0.06), txt(s, 20 * z, "medium", "text", "mono", 0.06))
                         for s in self.steps]
        src = self.p.get("source")
        self.src = self._source(src.get("label", "SOURCE"), src.get("text", "")) if src else None
        v = self.p.get("verdict")
        if v:
            self.stamp = stamp_sprite(v.get("verdict", "MYTH").upper(), z)
            self.v_color = VERDICTS.get(v.get("verdict", "MYTH").upper(), "myth")
            self.v_sub = self._stamp_sub(v["sub"]) if v.get("sub") else None
            self.flash = G.radial(int(1400 * z), self.v_color, 0.55, 1.4)
        self.setup_body()

    def setup_body(self):
        pass

    def _pill(self, rubric, number):
        z = self.z
        t = txt(str(rubric).upper(), 24 * z, "extrabold", "text", "head", 0.08)
        n = txt(str(number), 20 * z, "medium", "dim", "mono", 0.02) if number else None
        w = int(26 * z + 12 * z + 14 * z + t.width + (14 * z + n.width if n else 0) + 26 * z)
        h = int(56 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 179), outline=(255, 255, 255, 26), width=SS)
        pill = _down(img, w, h)
        dot = dot_glow(12 * z)
        pill.alpha_composite(dot, (int(26 * z + 6 * z - dot.width / 2), int(h / 2 - dot.height / 2)))
        x = int(26 * z + 12 * z + 14 * z)
        pill.alpha_composite(t, (x, int((h - t.height) / 2 + 2 * z)))
        if n:
            pill.alpha_composite(n, (x + t.width + int(14 * z), int((h - n.height) / 2 + 2 * z)))
        return pill

    def _source(self, label, text):
        z = self.z
        a = txt(label.upper(), 18 * z, "medium", "accent", "mono", 0.06)
        b = txt(text, 18 * z, "medium", "dim", "mono")
        w, h = int(18 * z + a.width + 12 * z + b.width + 18 * z), int(44 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 10 * z * SS, fill=(10, 13, 20, 179), outline=(255, 255, 255, 26), width=SS)
        chip = _down(img, w, h)
        chip.alpha_composite(a, (int(18 * z), int((h - a.height) / 2)))
        chip.alpha_composite(b, (int(18 * z + a.width + 12 * z), int((h - b.height) / 2)))
        return chip

    def _stamp_sub(self, text):
        """Подпись под штампом: моно 26 px, *акцент* — циан."""
        z = self.z
        f = G.font(int(26 * z), "medium", "mono")
        parts = re.split(r"(\*[^*]+\*)", text)
        w = int(sum(f.getlength(p.strip("*")) for p in parts) + 44 * z)
        h = int(26 * z * 1.25 + 20 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 10 * z * SS, fill=(10, 13, 20, 219), outline=(255, 255, 255, 26), width=SS)
        box = _down(img, w, h)
        d = ImageDraw.Draw(box)
        x = 22 * z
        for p in parts:
            hl = p.startswith("*")
            p = p.strip("*")
            d.text((x, 10 * z), p, font=f, fill=C("accent" if hl else "text"))
            x += f.getlength(p)
        return box

    # ---------- helpers
    def vdim(self, t):
        """На вердикте всё, кроме штампа, гаснет до 32 %."""
        if self.v_t is None:
            return 1.0
        return M.lerp(1, 0.32, M.ease_in_out(M.prog(t, self.v_t - 0.15, 0.35)))

    def gone(self, t, name):
        """Уход элемента в конце сцены, если его не переносим (keep)."""
        if name in self.keep or self.last:
            return 0.0
        return M.ease_in(M.prog(t, self.exit_t, M.fr(M.F_EXIT)))

    def card(self, img, t, spr, x, y, start, act=0.0, dim=1.0, frm="bottom", name=None, ph=0.0, T=0.0, ring=None):
        """Появление 14 кадров (сдвиг 24 px, размытие 8→0, масштаб 0,96→1) + idle-покачивание + уход."""
        z = self.z
        k = M.ease_out_expo(M.prog(t, start, M.fr(M.F_APPEAR)))
        if k <= 0:
            return 0.0
        xo = self.gone(t, name) if name else 0.0
        a = k * (1 - xo) * dim
        dx = (1 - k) * 32 * z if frm == "right" else 0
        dy = (1 - k) * 24 * z if frm == "bottom" else 0
        dy += xo * 12 * z + M.bob(T, ph) * k * z
        put(img, spr, x + dx, y + dy, a, 0.96 + 0.04 * k, (1 - k) * 8 + xo * 4)
        if ring is not None and act > 0.01:
            spr_r, pad = ring
            put(img, spr_r, x + dx - pad, y + dy - pad, a * act * M.pulse(T, ph) / 1.1, 0.96 + 0.04 * k)
        return k

    # ---------- кадр
    def draw(self, img, t, T):
        self.draw_chrome(img, t, T)
        self.draw_body(img, t, T)
        z = self.z
        if self.src is not None:
            put(img, self.src, 96 * z, self.H - 160 * z + M.bob(T, 0.2) * z,
                M.appear(t, self.src_t, self.exit_t if "source" not in self.keep and not self.last else None)[0] * self.vdim(t))
        self.draw_verdict(img, t, T)
        self.draw_neuron(img, t, T)

    def draw_body(self, img, t, T):
        pass

    def draw_chrome(self, img, t, T):
        z = self.z
        ch, prev = self.chrome, self.chrome_prev
        same = prev.get("rubric") == ch.get("rubric") and prev.get("number") == ch.get("number")
        if self.pill is not None:
            k = 1.0 if same else M.ease_out_expo(M.prog(t, 0.2, M.fr(M.F_APPEAR)))
            put(img, self.pill, 96 * z, 96 * z + (1 - k) * 24 * z + M.bob(T, 1) * z, k)
        clock = ch.get("clock")
        if clock:
            self.draw_clock(img, t, T, clock)
        elif self.steps:
            cur = int(ch.get("step", 0))
            if self.v_t is not None and "VERDICT" in self.steps:
                cur_v = self.steps.index("VERDICT")
            else:
                cur_v = None
            pstep = int(prev.get("step", cur)) if prev.get("steps") else cur
            k_in = 1.0 if prev.get("steps") else M.ease_out_expo(M.prog(t, 0.35, M.fr(M.F_APPEAR)))
            x = self.W - 96 * z
            items = []
            for i, (off, on) in enumerate(self.step_spr):
                items.append((i, off, on))
            # справа налево: ширина = текст + кружок 10 + 10 + промежуток 28
            widths = [on.width + 20 * z for _, _, on in items]
            x0 = x - sum(widths) - 28 * z * (len(items) - 1)
            y = 112 * z + M.bob(T, 2) * z
            for (i, off, on), w in zip(items, widths):
                f_cur = M.ease_in_out(M.prog(t, 0.0, M.fr(M.F_FOCUS)))
                lit = (1 - f_cur) * (i == pstep) + f_cur * (i == cur)
                if cur_v is not None:
                    fv = M.ease_in_out(M.prog(t, self.v_t, M.fr(M.F_FOCUS)))
                    lit = lit * (1 - fv) + fv * (i == cur_v)
                cy = y + on.height / 2
                r = 5 * z
                dd = ImageDraw.Draw(img, "RGBA")
                a = int(255 * k_in)
                dd.ellipse((x0 - r, cy - r, x0 + r, cy + r), outline=C("dim", int(a * (1 - lit))), width=max(1, int(1.5 * z)))
                if lit > 0.01:
                    put(img, dot_glow(10 * z), x0, cy, lit * k_in, anchor="c")
                put(img, off, x0 + 10 * z, y, k_in * (1 - lit))
                put(img, on, x0 + 10 * z, y, k_in * lit)
                x0 += w + 28 * z

    def draw_clock(self, img, t, T, clock):
        """Часы дня §8.6: циферблат справа сверху, стрелка доезжает до времени новой главы."""
        z = self.z
        face = clock_face(z)
        m1 = _minutes(clock)
        m0 = _minutes(self.state.get("lab_clock")) if self.state.get("lab_clock") else m1
        k = M.ease_in_out(M.prog(t, 0.3, 1.2))
        mins = M.lerp(m0, m1, k) if m0 is not None and m1 is not None else 0
        cx, cy = self.W - 96 * z - face.width / 2, 96 * z + face.height / 2 + M.bob(T, 3) * z
        put(img, face, cx, cy, 1.0, anchor="c")
        d = ImageDraw.Draw(img, "RGBA")
        for ang, ln, wd in ((mins / 720 * math.tau, 0.24, 4), ((mins % 60) / 60 * math.tau, 0.34, 3)):
            r = face.width * ln
            d.line((cx, cy, cx + r * math.sin(ang), cy - r * math.cos(ang)), fill=C("text"), width=int(wd * z))
        d.ellipse((cx - 4 * z, cy - 4 * z, cx + 4 * z, cy + 4 * z), fill=C("accent"))
        hh, mm = int(mins // 60) % 24, int(mins % 60)
        lab = txt(f"{hh:02d}:{mm:02d}", 22 * z, "medium", "text", "mono")
        put(img, lab, cx - face.width / 2 - 14 * z - lab.width, cy - lab.height / 2, 1.0)

    def draw_verdict(self, img, t, T):
        if self.v_t is None or t < self.v_t - 0.2:
            return
        z = self.z
        f = M.prog(t, self.v_t - 0.05, 0.7)
        put(img, self.flash, self.W / 2, self.H * 0.44, math.sin(f * math.pi) * 0.9, anchor="c")
        k = M.spring(M.prog(t, self.v_t, M.fr(M.F_STAMP) + 0.25))
        a = min(1.0, k * 2)
        # масштаб 1,4→1, поворот к −8° (против часовой; у PIL положительный угол — против часовой)
        put(img, self.stamp, self.W / 2, self.H * 0.42, a, M.lerp(1.4, 1.0, k), rot=M.lerp(14, 8, k), anchor="c")
        if self.v_sub is not None:
            sk = M.ease_out_expo(M.prog(t, self.v_t + 0.45, M.fr(M.F_APPEAR)))
            box_h = self.stamp.height - 2 * int(40 * z * 2.5)  # без отступа свечения
            put(img, self.v_sub, self.W / 2, self.H * 0.42 + box_h / 2 + 22 * z + self.v_sub.height / 2 + (1 - sk) * 16 * z,
                sk, anchor="c")

    def draw_neuron(self, img, t, T):
        if self.n_t is None or t < self.n_t:
            return
        z = self.z
        n = self.p.get("neuron") or {}
        mood = n.get("mood", "surprised")
        k = M.spring(M.prog(t, self.n_t, 0.6))
        sur = M.ease_out_expo(M.prog(t, self.n_t + 0.1, 0.3)) * (1 - M.ease_in_out(M.prog(t, self.n_t + 1.4, 0.4)))
        blink = self.n_t + 1.0 < t < self.n_t + 1.12
        spr = neuron_sprite(mood if sur > 0.5 or mood == "facepalm" else "neutral", blink, z)
        x, y = n.get("x", 830), n.get("y", 700)
        nod = math.sin(M.prog(t, self.n_t + 0.4, 0.8) * math.tau * 2) * 8 * z if mood == "nod" else 0
        put(img, spr, x * z + 85 * z, y * z + 85 * z + M.bob(T, 4) * k * z + nod, min(1.0, k * 1.6) * (1 - self.gone(t, "neuron")),
            M.lerp(0.4, 1, k), rot=math.sin(T * 2.2) * 3 * k, anchor="c")


# ===================================================================== hero number (shared)
class HeroMixin:
    """Огромная цифра (Unbounded 300 px) + подпись; счётчик; «Миф → Реальность» с зачёркиванием цветом MYTH.
    hero: {value, from, caption, sub, color: text|accent, at, from_prev, strike_at}."""

    def hero_plan(self):
        h = self.p.get("hero")
        self.hero = h
        if not h:
            return
        self.prev_hero = self.state.get("lab_hero") if h.get("from_prev") else None
        self.h_t = self.at(h.get("at"), 0.4)
        if self.prev_hero:
            self.h_strike = self.at(h.get("strike_at"), self.h_t - 0.45)
            self.h_from = float(h.get("from", self.prev_hero.get("value", 0)))
        else:
            self.h_strike = None
            self.h_from = float(h.get("from", 0))

    def hero_out(self):
        h = self.p.get("hero")
        if not h:
            return None
        return {"value": h.get("value"), "caption": h.get("caption", ""), "sub": h.get("sub", ""),
                "color": h.get("color", "text"), "x": h.get("x", 120), "y": h.get("y", 470)}

    def hero_sfx(self):
        if not self.hero:
            return []
        ev = [(self.h_t, "pop")] + self.ticks(self.h_t + 0.05, 0.9)
        if self.h_strike is not None:
            ev.append((self.h_strike, "swish"))
        return ev

    def _num(self, v, color, z):
        s = f"{int(round(v))}" if isinstance(v, (int, float)) else str(v)
        return num_sprite(s, color, z, 300)

    def _cap(self, cap, sub, z):
        a = txt(str(cap).upper(), 34 * z, "extrabold", "text", "head", 0.08) if cap else None
        b = txt(sub, 20 * z, "medium", "dim", "mono", 0.02) if sub else None
        return a, b

    def _draw_num(self, img, n, x, y, alpha, scale=1.0, blur=0.0):
        """Положить цифру так, чтобы ЧЕРНИЛА начинались в (x, y); масштаб — от левого верхнего угла (как в демо)."""
        spr, off, iw, ih = n
        cx = x + (iw / 2) * scale
        cy = y + (ih / 2) * scale
        put(img, spr, cx, cy, alpha, scale, blur, anchor="c")

    def _strike(self, img, x, y, n, scale, k, alpha):
        """Зачёркивание цветом MYTH: от левого края цифры на 110 % её ширины, по середине высоты."""
        z = self.z
        _, _, iw, ih = n
        bw = int((iw * 1.1 + 28 * z) * scale * k)
        if bw > 2:
            bar = strike_bar(bw, max(2, int(14 * z * scale)), z)
            pad = (bar.height - max(2, int(14 * z * scale))) / 2
            put(img, bar, x - 14 * z * scale - pad, y + ih * 0.5 * scale - bar.height / 2, alpha)

    def draw_hero(self, img, t, T, dim=1.0, focus=1.0):
        h = self.hero
        if not h:
            return
        z = self.z
        # (x, y) из params — верх блока как в демо (top: 470); чернила цифры начинаются на 34 px ниже
        x, y = h.get("x", 120) * z, h.get("y", 470) * z + 34 * z
        if self.prev_hero:
            ph = self.prev_hero
            m = M.ease_in_out(M.prog(t, self.h_t - 0.1, 0.55))
            n = self._num(ph["value"], ph.get("color", "text"), z)
            a = M.lerp(1, 0.55, m) * dim
            sc = M.lerp(1, 0.32, m)
            px, py = x + M.lerp(0, 520, m) * z, y + M.lerp(0, 10, m) * z + M.bob(T, 2) * z
            self._draw_num(img, n, px, py, a, sc)
            ca, cb = self._cap(ph.get("caption"), ph.get("sub"), z)
            cy = y + n[3] + 42 * z
            put(img, ca, x, cy, (1 - m) * dim)
            put(img, cb, x, cy + 46 * z, (1 - m) * dim)
            sk = M.ease_in_out(M.prog(t, self.h_strike, M.fr(M.F_FOCUS)))
            if sk > 0:
                self._strike(img, px, py, n, sc, sk, a)
        k = M.ease_out_expo(M.prog(t, self.h_t, M.fr(M.F_APPEAR)))
        if k <= 0:
            return
        v = M.count(t, self.h_t, self.h_from, float(h.get("value", 0))) \
            if isinstance(h.get("value"), (int, float)) else h.get("value")
        n = self._num(v, h.get("color", "text"), z)
        xo = self.gone(t, "hero")
        a = k * (1 - xo) * dim * M.lerp(0.65, 1, focus)
        yy = y + (1 - k) * 24 * z + M.bob(T, 2) * k * z + xo * 12 * z
        self._draw_num(img, n, x, yy, a, 0.96 + 0.04 * k, (1 - k) * 8)
        ca, cb = self._cap(h.get("caption"), h.get("sub"), z)
        cy = yy + n[3] + 42 * z
        put(img, ca, x, cy, a)
        put(img, cb, x, cy + 46 * z, a)
        if h.get("strike_at") is not None and not self.prev_hero:
            sk = M.ease_in_out(M.prog(t, self.at(h["strike_at"], self.D), M.fr(M.F_FOCUS)))
            if sk > 0:
                self._strike(img, x, yy, n, 1.0, sk, a)


@functools.lru_cache(maxsize=256)
def num_sprite(s, color, z, size):
    """Огромная цифра Unbounded 800 со свечением. -> (спрайт, отступ до чернил, ширина и высота чернил)."""
    f = G.font(int(size * z), "extrabold", "num")
    l, t, r, b = f.getbbox(s)
    p = int(8 * z)
    base = Image.new("RGBA", (r - l + 2 * p, b - t + 2 * p), (0, 0, 0, 0))
    ImageDraw.Draw(base).text((p - l, p - t), s, font=f, fill=C(color))
    rad = (60 if color == "accent" else 40) * z
    spr = G.glowify(base, color, rad, 0.45 if color == "accent" else 0.15)
    return spr, (spr.width - base.width) // 2 + p, r - l, b - t


@functools.lru_cache(maxsize=64)
def strike_bar(w, h, z):
    return G.glowify(G.rrect((w, h), h // 2, C("myth")), "myth", 14 * z, 0.6)


# ===================================================================== templates §5
def _focus_list(times, end):
    """Фокус: элемент i активен от своего времени до времени следующего."""
    out = []
    for i, t0 in enumerate(times):
        t1 = times[i + 1] if i + 1 < len(times) else end
        out.append((t0, t1))
    return out


@template("lab_hero_stack",
          doc="lab · Hero + Stack: слева огромная цифра (счётчик, «миф → реальность»), справа стопка 3–4 карточек, "
              "линии с бегущими точками от цифры к карточкам; опц. карточка утверждения сверху-слева.",
          params={"claim": {"label": "VIRAL CLAIM", "text": "“It takes *21 days* to build a habit.”", "meta": "", "at": "w:says", "qmark": True},
                  "hero": {"value": 21, "from": 0, "caption": "days", "sub": "the popular claim", "color": "text", "at": "21"},
                  "cards": [{"icon": "book", "title": "Title", "sub": "mono subtitle", "chip": None, "chip_color": "noev", "at": "w:book"}],
                  "lines": True, **LabTemplate.COMMON},
          beats="каждый элемент — по своему `at` (слово/бит/секунды); без `at` — стаггер")
class LabHeroStack(HeroMixin, LabTemplate):
    def plan_body(self):
        self.hero_plan()
        c = self.p.get("claim")
        self.c_t = self.at(c.get("at"), 0.4) if c else None
        self.q_t = self.c_t + 0.55 if c and c.get("qmark", True) else None
        self.cards = self.p.get("cards") or []
        self.k_t = self.seq_times(self.cards, (self.h_t if self.hero else 0.6) + 0.8)
        order = [x for x in [self.c_t, self.h_t if self.hero else None] + self.k_t if x is not None]
        self.fl = _focus_list(sorted(order), self.exit_t)

    def sfx_body(self):
        ev = self.hero_sfx() if self.hero else []
        if self.c_t is not None:
            ev.append((self.c_t, "pop"))
        if self.q_t is not None:
            ev.append((self.q_t, "pop"))
        ev += [(x, "pop") for x in self.k_t]
        return ev

    def setup_body(self):
        z = self.z
        c = self.p.get("claim")
        if c:
            w = int((780 + 72) * z)  # как в демо: 780 — ширина текста, плюс поля 36 + 36
            lab = txt(c.get("label", "VIRAL CLAIM"), 20 * z, "medium", "dim", "mono", 0.08)
            body = rich(c.get("text", ""), 46 * z, 780 * z)
            meta = txt(c["meta"], 19 * z, "medium", "dim", "mono") if c.get("meta") else None
            h = int(30 * z + lab.height + 12 * z + body.height + (14 * z + meta.height if meta else 0) + 30 * z)
            card = glass(w, h, int(18 * z)).copy()
            y = int(30 * z)
            card.alpha_composite(lab, (int(36 * z), y)); y += lab.height + int(12 * z)
            card.alpha_composite(body, (int(36 * z), y)); y += body.height + int(14 * z)
            if meta:
                card.alpha_composite(meta, (int(36 * z), y))
            self.claim_spr = card
            self.claim_ring = ring_pad(w, h, int(18 * z))
            q = int(76 * z)
            img, d = _ss_canvas(q, q)
            d.ellipse((SS, SS, q * SS - SS, q * SS - SS), fill=C("bg"), outline=C("noev"), width=int(3 * z * SS))
            qs = _down(img, q, q)
            qm = txt("?", 38 * z, "extrabold", "noev", "num")
            qs.alpha_composite(qm, ((q - qm.width) // 2 + int(2 * z), (q - qm.height) // 2 - int(2 * z)))
            self.qmark = qs
        self.card_spr = []
        for it in self.cards:
            w, h = int(724 * z), int(120 * z)
            card = glass(w, h, int(18 * z)).copy()
            tl = tile(it.get("icon", "book"), int(72 * z))
            card.alpha_composite(tl, (int(26 * z), (h - tl.height) // 2))
            t1 = txt(it.get("title", ""), 32 * z, "extrabold", "text", "head", 0.01)
            t2 = txt(it.get("sub", ""), 19 * z, "medium", "dim", "mono") if it.get("sub") else None
            x = int(26 * z + tl.width + 24 * z)
            th = t1.height + (6 * z + t2.height if t2 else 0)
            y = int((h - th) / 2)
            card.alpha_composite(t1, (x, y))
            if it.get("chip"):
                cc = it.get("chip_color", "noev")
                cp = txt(it["chip"], 17 * z, "medium", cc, "mono")
                cw, chh = int(cp.width + 24 * z), int(cp.height + 6 * z)
                im2, d2 = _ss_canvas(cw, chh)
                d2.rounded_rectangle((0, 0, cw * SS - 1, chh * SS - 1), chh * SS / 2, outline=C(cc), width=int(1.5 * z * SS))
                chip = _down(im2, cw, chh)
                chip.alpha_composite(cp, (int(12 * z), int(3 * z)))
                card.alpha_composite(chip, (x + t1.width + int(10 * z), y + int((t1.height - chh) / 2 + 3 * z)))
            if t2:
                card.alpha_composite(t2, (x, int(y + t1.height + 6 * z)))
            self.card_spr.append((card, ring_pad(w, h, int(18 * z))))

    def _ys(self):
        z = self.z
        n = len(self.cards)
        top = 330 if n <= 3 else 260
        return [(top + i * 148) * z for i in range(n)]

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {}
        for (a, b) in self.fl:
            foc[a] = M.focus(t, a, b)
        if self.p.get("claim"):
            br, act = foc.get(self.c_t, (1, 0))
            self.card(img, t, self.claim_spr, 96 * z, 184 * z, self.c_t, act, br * vd, name="claim", ph=0.4, T=T, ring=self.claim_ring)
            if self.q_t is not None:
                k = M.spring(M.prog(t, self.q_t, 0.6))
                a = min(1, k * 1.5) * (1 - self.gone(t, "claim")) * br * vd
                put(img, self.qmark, 96 * z + self.claim_spr.width - 26 * z + 38 * z, 184 * z - 26 * z + 38 * z, a,
                    M.lerp(1.6, 1, k), rot=M.lerp(20, 0, k), anchor="c")
        if self.hero:
            br, act = foc.get(self.h_t, (1, 0))
            self.draw_hero(img, t, T, vd, act if self.fl else 1)
        ys = self._ys()
        d = ImageDraw.Draw(img, "RGBA")
        hx, hy = 700 * z, 600 * z
        for i, (it, (spr, ring), y) in enumerate(zip(self.cards, self.card_spr, ys)):
            t0 = self.k_t[i]
            br, act = foc.get(t0, (1, 0))
            if self.p.get("lines", True) and self.hero:
                self._line(img, d, t, (hx, hy), (1100 * z, y + 60 * z), t0 - 0.25, act, self.gone(t, f"card{i}") or self.gone(t, "cards"))
            self.card(img, t, spr, 1100 * z, y, t0, act, br * vd, "right", name="cards", ph=i, T=T, ring=ring)

    def _line(self, img, d, t, p0, p1, start, act, xo):
        """Кривая от источника к цели (ease-in-out, 22 кадра), узел на конце, бегущие точки."""
        z = self.z
        k = M.line_progress(t, start)
        if k <= 0 or xo >= 1:
            return
        (x0, y0), (x1, y1) = p0, p1
        pts = []
        N = 48
        for i in range(N + 1):
            u = i / N
            # cubic: (x0,y0) (x0+200,y0) (x1-180,y1) (x1,y1) — как в демо
            cx0, cy0, cx1, cy1 = x0 + 200 * z, y0, x1 - 180 * z, y1
            bx = (1 - u) ** 3 * x0 + 3 * (1 - u) ** 2 * u * cx0 + 3 * (1 - u) * u * u * cx1 + u ** 3 * x1
            by = (1 - u) ** 3 * y0 + 3 * (1 - u) ** 2 * u * cy0 + 3 * (1 - u) * u * u * cy1 + u ** 3 * y1
            pts.append((bx, by))
        n = max(2, int(N * k) + 1)
        a = (1 - xo) * M.lerp(0.5, 1, act) * self.vdim(t)
        for i in range(n - 1):
            g = 0.15 + 0.75 * i / N
            d.line((pts[i], pts[i + 1]), fill=C("accent", int(255 * g * a)), width=max(1, int(2.5 * z)))
        if k >= 1:
            ex, ey = pts[-1]
            d.ellipse((ex - 7 * z, ey - 7 * z, ex + 7 * z, ey + 7 * z), fill=C("bg"), outline=C("accent", int(255 * a)), width=int(3 * z))
            for u, al in M.running_dot(t, start + M.fr(M.F_LINE)):
                px, py = pts[min(N, int(u * N))]
                d.ellipse((px - 6 * z, py - 6 * z, px + 6 * z, py + 6 * z), fill=C("accent", int(255 * al * a)))


@template("lab_crowd",
          doc="lab · Crowd: толпа из N иконок = реальная выборка, подсветка отдельных людей с ярлыками; "
              "опц. карточка исследования, шкала-диапазон и цифра слева (может морфить цифру прошлой сцены).",
          params={"hero": {"value": 66, "from_prev": True, "caption": "median days", "sub": "", "color": "accent", "at": "66", "strike_at": "w:took"},
                  "study": {"authors": "Lally, van Jaarsveld, Potts & Wardle", "where": "Eur. J. of Social Psychology · 2010 · n = 96", "evidence": 3, "at": "2010"},
                  "crowd": {"n": 96, "cols": 16, "at": "96", "highlight": [{"index": 19, "label": "18 days", "color": "accent", "at": "18"}]},
                  "range": {"min": 18, "max": 254, "mark": 66, "min_label": "18 days", "max_label": "~254 days", "mark_label": "66 · median", "at": "66"},
                  **LabTemplate.COMMON},
          beats="элементы — по `at`; люди толпы появляются волной за ~0,6 с")
class LabCrowd(HeroMixin, LabTemplate):
    def plan_body(self):
        self.hero_plan()
        st, cr, rg = self.p.get("study"), self.p.get("crowd"), self.p.get("range")
        self.s_t = self.at(st.get("at"), 0.3) if st else None
        self.cr_t = self.at(cr.get("at"), (self.s_t or 0.3) + 0.3) if cr else None
        self.hl = []
        if cr:
            for i, h in enumerate(cr.get("highlight") or []):
                self.hl.append((h, self.at(h.get("at"), self.cr_t + 1.5 + 0.4 * i)))
        self.r_t = self.at(rg.get("at"), self.D * 0.6) if rg else None
        order = [x for x in (self.s_t, self.r_t, self.h_t if self.hero else None) if x is not None]
        self.fl = _focus_list(sorted(order), self.v_t or self.exit_t)

    def sfx_body(self):
        ev = self.hero_sfx() if self.hero else []
        ev += [(x, "pop") for x in (self.s_t, self.cr_t, self.r_t) if x is not None]
        ev += [(t0, "tick") for _, t0 in self.hl]
        return ev

    def setup_body(self):
        z = self.z
        st = self.p.get("study")
        self.study = study_card(st.get("authors", ""), st.get("where", ""), int(st.get("evidence", 3)), z) if st else None
        self.study_ring = ring_pad(self.study.width, self.study.height, int(18 * z)) if st else None
        cr = self.p.get("crowd")
        if cr:
            n = int(cr.get("n", 96))
            self.scale_note = None
            if n > 400:
                self.scale_note = txt(f"1 icon = {int(math.ceil(n / 400))} people", 18 * z, "medium", "dim", "mono")
                n = int(math.ceil(n / math.ceil(n / 400)))
            cols = int(cr.get("cols", 16 if n <= 128 else 24))
            rows = int(math.ceil(n / cols))
            area_w = 724 * z
            area_h = (300 if not self.p.get("range") else 300) * z
            cw = area_w / cols
            ch = min(50 * z, area_h / rows)
            pw = min(30 * z, cw * 0.66)
            self.pw, self.ph = int(pw), int(pw * 1.2)
            self.cells = [((i % cols) * cw, (i // cols) * ch, (i % cols) * 0.045 + (i // cols) * 0.03) for i in range(n)]
            self.p_white = person_icon(self.pw, self.ph, "text")
            self.p_col = {c: person_icon(self.pw, self.ph, c) for c in ("accent", "accent2", "true", "myth", "half")}
            self.tags = []
            for h, t0 in self.hl:
                c = h.get("color", "accent")
                lab = txt(h.get("label", ""), 18 * z, "medium", "bg", "mono")
                w, hh = int(lab.width + 20 * z), int(lab.height + 8 * z)
                im, d = _ss_canvas(w, hh)
                d.rounded_rectangle((0, 0, w * SS - 1, hh * SS - 1), 8 * z * SS, fill=C(c))
                tg = _down(im, w, hh)
                tg.alpha_composite(lab, (int(10 * z), int(4 * z)))
                self.tags.append(tg)
        rg = self.p.get("range")
        if rg:
            self.rl = txt(rg.get("min_label", str(rg.get("min"))), 19 * z, "medium", "dim", "mono")
            self.rr = txt(rg.get("max_label", str(rg.get("max"))), 19 * z, "medium", "dim", "mono")
            self.rm = txt(rg.get("mark_label", str(rg.get("mark"))), 19 * z, "medium", "accent", "mono")
            w = int(724 * z)
            grad = np.zeros((max(2, int(4 * z)), w, 4), np.uint8)
            c1, c2 = np.array(G.PAL["accent"]), np.array(G.PAL["accent2"])
            for x in range(w):
                grad[:, x, :3] = c1 + (c2 - c1) * x / max(1, w - 1)
            grad[:, :, 3] = 255
            self.track = Image.fromarray(grad, "RGBA")

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        if self.hero:
            self.draw_hero(img, t, T, vd * (M.lerp(1, 0.55 / 0.32, M.ease_in_out(M.prog(t, (self.v_t or 1e9) - 0.15, 0.35))) if self.v_t else 1),
                           foc.get(self.h_t, (1, 0))[1] if self.fl else 1)
        if self.study is not None:
            br, act = foc.get(self.s_t, (1, 0))
            self.card(img, t, self.study, 1100 * z, 184 * z, self.s_t, act, br * vd, "right", name="study", ph=1.7, T=T, ring=self.study_ring)
        if self.p.get("crowd"):
            x0, y0 = 1100 * z, 420 * z
            xo = self.gone(t, "crowd")
            for i, (cx, cy, dl) in enumerate(self.cells):
                k = M.ease_out_expo(M.prog(t, self.cr_t + dl, 0.3))
                if k <= 0:
                    continue
                spr, s, a = self.p_white, 1.0, k * 0.72
                for j, (h, t0) in enumerate(self.hl):
                    if h.get("index") == i:
                        hk = M.ease_out_expo(M.prog(t, t0, 0.35))
                        if hk > 0:
                            spr, s, a = self.p_col.get(h.get("color", "accent"), self.p_white), M.lerp(1, 1.35, hk), M.lerp(a, 1, hk)
                put(img, spr, x0 + cx, y0 + cy + (1 - k) * 12 * z, a * vd * (1 - xo), s)
            for j, (h, t0) in enumerate(self.hl):
                i = h.get("index", 0)
                if i >= len(self.cells):
                    continue
                cx, cy, _ = self.cells[i]
                k = M.spring(M.prog(t, t0, 0.5))
                tg = self.tags[j]
                put(img, tg, x0 + cx + self.pw / 2, y0 + cy - 34 * z + tg.height / 2 * 0, min(1, k * 1.4) * vd * (1 - xo),
                    M.lerp(0.6, 1, k), anchor="c")
            if self.scale_note is not None:
                put(img, self.scale_note, x0, y0 - 30 * z, M.appear(t, self.cr_t)[0] * vd)
        rg = self.p.get("range")
        if rg:
            br, act = foc.get(self.r_t, (1, 0))
            k = M.ease_in_out(M.prog(t, self.r_t, 0.55))
            if k > 0:
                xo = self.gone(t, "range")
                a = M.lerp(0.7, 1, act) * vd * (1 - xo)
                x0, y0 = 1100 * z, 752 * z
                tw = int(self.track.width * k)
                if tw > 1:
                    put(img, self.track.crop((0, 0, tw, self.track.height)), x0, y0 + 30 * z, a)
                put(img, self.rl, x0, y0 + 48 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.05, 0.3)) * a)
                put(img, self.rr, x0 + self.track.width - self.rr.width, y0 + 48 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.4, 0.3)) * a)
                lo, hi, mk = float(rg.get("min", 0)), float(rg.get("max", 1)), float(rg.get("mark", 0))
                mx = x0 + self.track.width * (mk - lo) / max(1e-6, hi - lo)
                sk = M.spring(M.prog(t, self.r_t + 0.35, 0.5))
                if sk > 0:
                    d = ImageDraw.Draw(img, "RGBA")
                    r = 18 * z * M.lerp(0.3, 1, sk)
                    cy = y0 + 32 * z
                    ring = G.glowify(G.rrect((int(2 * r) + 1, int(2 * r) + 1), int(r), C("bg"), C("accent"), max(2, int(4 * z))), "accent", 12 * z, 0.6)
                    put(img, ring, mx, cy, min(1, sk * 1.5) * a, anchor="c")
                    put(img, self.rm, mx - self.rm.width / 2, y0 - 30 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.5, 0.3)) * a)


@template("lab_verdict",
          doc="lab · Вердикт отдельной сценой: штамп TRUE/HALF-TRUE/MYTH/NO EVIDENCE падает пружиной, вспышка цвета "
              "вердикта, подпись; перенесённая цифра (keep: [hero]) видна приглушённой. Разрыв ритма.",
          params={"verdict": {"verdict": "MYTH", "sub": "21 days → median *66*", "at": "w:verdict"}, "neuron": None,
                  "chrome": None, "keep": [], "source": None},
          beats="штамп — по verdict.at (по умолчанию 0,3 с)")
class LabVerdict(HeroMixin, LabTemplate):
    def plan_body(self):
        if not self.p.get("verdict"):
            self.p = dict(self.p, verdict={"verdict": "MYTH"})
            self.v_t = 0.3
        self.carry = self.state.get("lab_hero")

    def draw_body(self, img, t, T):
        if self.carry:
            z = self.z
            n = self._num(self.carry["value"], self.carry.get("color", "text"), z)
            self._draw_num(img, n, self.carry.get("x", 120) * z, (self.carry.get("y", 470) + 34) * z + M.bob(T, 2) * z, 0.55)


@template("lab_full_number",
          doc="lab · Full Number: одна цифра на весь кадр + подпись; опц. «миф → реальность» (myth: зачёркнутое "
              "мифическое значение, счётчик доматывает до реального). Разрыв ритма, шок-факт.",
          params={"value": 66, "from": 0, "prefix": "", "suffix": "", "caption": "days", "sub": "", "color": "accent",
                  "at": 0, "myth": None, **LabTemplate.COMMON},
          beats="счёт — от `at`; myth: {value, strike_at}")
class LabFullNumber(LabTemplate):
    def plan_body(self):
        self.n_at = self.at(self.p.get("at", 0), 0.3)
        my = self.p.get("myth")
        if my:  # «Миф → Реальность»: сначала мифическое значение, зачёркивание, счётчик доматывает до реального
            self.show_t = self.at(my.get("at"), 0.3)
            self.m_strike = self.at(my.get("strike_at"), self.show_t + 0.6)
            self.c_at = max(self.n_at, self.m_strike + 0.45)
        else:
            self.show_t, self.m_strike, self.c_at = self.n_at, None, self.n_at

    def sfx_body(self):
        ev = [(self.show_t, "pop")]
        if self.m_strike is not None:
            ev.append((self.m_strike, "swish"))
        return ev + self.ticks(self.c_at + 0.05, 0.9)

    def setup_body(self):
        z = self.z
        p = self.p
        self.cap = txt(str(p.get("caption", "")).upper(), 44 * z, "extrabold", "text", "head", 0.08) if p.get("caption") else None
        self.sub = txt(p["sub"], 22 * z, "medium", "dim", "mono") if p.get("sub") else None

    def _spr(self, s, color):
        z = self.z
        spr = G.text_sprite(s, int(320 * z), "extrabold", color, family="num")
        return G.glowify(spr, color, 60 * z, 0.4)

    def draw_body(self, img, t, T):
        z = self.z
        p = self.p
        vd = self.vdim(t)
        my = p.get("myth")
        cx, cy = self.W / 2, self.H * 0.44
        k = M.ease_out_expo(M.prog(t, self.show_t, M.fr(M.F_APPEAR)))
        if k <= 0:
            return
        xo = self.gone(t, "number")
        a = k * (1 - xo) * vd
        if my:
            v = M.count(t, self.c_at, float(my.get("value", 0)), float(p.get("value", 0))) if t >= self.c_at else float(my.get("value", 0))
            col = "text" if t < self.c_at else p.get("color", "accent")
        else:
            v = M.count(t, self.n_at, float(p.get("from", 0)), float(p.get("value", 0)))
            col = p.get("color", "accent")
        s = f"{p.get('prefix', '')}{int(round(v))}{p.get('suffix', '')}"
        spr = self._spr(s, col)
        put(img, spr, cx, cy + (1 - k) * 24 * z + M.bob(T, 1) * z, a, (0.96 + 0.04 * k) * (1 + 0.02 * M.pulse(T) - 0.02), (1 - k) * 8, anchor="c")
        if my and self.m_strike is not None:
            sk = M.ease_in_out(M.prog(t, self.m_strike, M.fr(M.F_FOCUS))) * (1 - M.prog(t, self.c_at, M.fr(4)))
            bw = int(spr.width * 0.7 * sk)
            if bw > 2:
                bar = G.glowify(G.rrect((bw, int(16 * z)), int(8 * z), C("myth")), "myth", 14 * z, 0.6)
                put(img, bar, cx - spr.width * 0.35, cy - 8 * z, a)
        y = cy + spr.height * 0.42
        if self.cap is not None:
            ck = M.ease_out_expo(M.prog(t, self.c_at + 0.25, M.fr(M.F_APPEAR)))
            put(img, self.cap, cx, y + (1 - ck) * 16 * z, ck * a, anchor="c")
        if self.sub is not None:
            sk = M.ease_out_expo(M.prog(t, self.c_at + 0.45, M.fr(M.F_APPEAR)))
            put(img, self.sub, cx, y + 56 * z, sk * a, anchor="c")


@template("lab_versus",
          doc="lab · Versus: две колонки «Думают / Нашли», посередине разделитель; пункты — карточки по `at`. "
              "Для проверки мифа.",
          params={"left": {"title": "THEY SAY", "items": [{"text": "21 days", "at": 0}]},
                  "right": {"title": "STUDIES FOUND", "items": [{"text": "66 days (median)", "at": 1}]},
                  **LabTemplate.COMMON},
          beats="пункты — по `at`, без `at` — стаггер")
class LabVersus(LabTemplate):
    def plan_body(self):
        L, R = self.p.get("left") or {}, self.p.get("right") or {}
        self.lt = self.seq_times(L.get("items") or [], 0.5)
        self.rt = self.seq_times(R.get("items") or [], (self.lt[-1] if self.lt else 0.5) + 0.6)
        self.fl = _focus_list(sorted(self.lt + self.rt), self.v_t or self.exit_t)

    def sfx_body(self):
        return [(0.3, "pop")] + [(x, "pop") for x in self.lt + self.rt]

    def setup_body(self):
        z = self.z
        L, R = self.p.get("left") or {}, self.p.get("right") or {}
        self.heads = [self._head(L.get("title", "THEY SAY"), "accent2"), self._head(R.get("title", "STUDIES FOUND"), "accent")]
        self.items = [[self._item(i.get("text", ""), c) for i in (side.get("items") or [])]
                      for side, c in ((L, "accent2"), (R, "accent"))]

    def _head(self, s, c):
        z = self.z
        t = txt(s.upper(), 26 * z, "extrabold", c, "head", 0.08)
        w, h = int(t.width + 52 * z), int(56 * z)
        im, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 179), outline=C(c, 140), width=int(1.5 * z * SS))
        p = _down(im, w, h)
        p.alpha_composite(t, (int(26 * z), int((h - t.height) / 2 + 2 * z)))
        return p

    def _item(self, s, c):
        z = self.z
        w = int(760 * z)
        tx = G.text_sprite(s, int(34 * z), "bold", "text", family="head", align="left", maxw=int(w - 80 * z))
        h = int(tx.height + 52 * z)
        card = glass(w, h, int(18 * z)).copy()
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((int(22 * z), int(22 * z), int(28 * z), h - int(22 * z)), int(3 * z), fill=C(c))
        card.alpha_composite(tx, (int(48 * z), int(26 * z)))
        return card, ring_pad(w, h, int(18 * z), c)

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        xs = (96 * z, self.W / 2 + 48 * z)
        for side in (0, 1):
            k = M.appear(t, 0.3 + 0.12 * side, None)[0] * (1 - self.gone(t, "versus"))
            put(img, self.heads[side], xs[side], 210 * z + M.bob(T, side) * z, k * vd)
            y = 300 * z
            times = self.lt if side == 0 else self.rt
            for (spr, ring), t0 in zip(self.items[side], times):
                br, act = foc.get(t0, (1, 0))
                self.card(img, t, spr, xs[side], y, t0, act, br * vd, "bottom" if side == 0 else "right", name="versus",
                          ph=side + y / 300, T=T, ring=ring)
                y += spr.height + 22 * z
        dk = M.line_progress(t, 0.2, 27) * (1 - self.gone(t, "versus"))
        if dk > 0:
            d = ImageDraw.Draw(img, "RGBA")
            x = self.W / 2
            d.line((x, 210 * z, x, 210 * z + 640 * z * dk), fill=(255, 255, 255, int(40 * vd)), width=max(1, int(2 * z)))
            vs = txt("VS", 22 * z, "extrabold", "dim", "num")
            put(img, vs, x, 180 * z, dk * vd, anchor="c")


@template("lab_flow",
          doc="lab · Flow: 3 станции слева направо, соединены линиями с бегущими точками; процесс, «как это работает».",
          params={"stations": [{"icon": "alarm", "title": "Cue", "sub": "same time, same place", "at": 0}], **LabTemplate.COMMON},
          beats="станция i — по `at`; линия к ней рисуется перед её появлением")
class LabFlow(LabTemplate):
    def plan_body(self):
        self.st = self.p.get("stations") or []
        self.tt = self.seq_times(self.st, 0.5)
        self.fl = _focus_list(self.tt, self.v_t or self.exit_t)

    def sfx_body(self):
        return [(x, "pop") for x in self.tt]

    def setup_body(self):
        z = self.z
        n = max(1, len(self.st))
        gap = 120 * z
        self.cw = int((self.W - 2 * 96 * z - gap * (n - 1)) / n)
        self.spr = []
        for s in self.st:
            w = self.cw
            tl = tile(s.get("icon", "check"), int(72 * z))
            t1 = G.text_sprite(s.get("title", ""), int(36 * z), "extrabold", "text", family="head", align="left", maxw=int(w - 56 * z))
            t2 = G.text_sprite(s["sub"], int(20 * z), "medium", "dim", family="mono", align="left", maxw=int(w - 56 * z)) if s.get("sub") else None
            h = int(28 * z + tl.height + 18 * z + t1.height + (8 * z + t2.height if t2 else 0) + 28 * z)
            card = glass(w, h, int(18 * z)).copy()
            card.alpha_composite(tl, (int(28 * z), int(28 * z)))
            y = int(28 * z + tl.height + 18 * z)
            card.alpha_composite(t1, (int(24 * z), y))
            if t2:
                card.alpha_composite(t2, (int(24 * z), int(y + t1.height + 8 * z)))
            self.spr.append((card, ring_pad(w, h, int(18 * z))))
        self.gap = gap

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        d = ImageDraw.Draw(img, "RGBA")
        cy = self.H * 0.47
        x = 96 * z
        prev = None
        for i, ((spr, ring), t0) in enumerate(zip(self.spr, self.tt)):
            y = cy - spr.height / 2
            br, act = foc.get(t0, (1, 0))
            if prev is not None:
                xo = self.gone(t, "flow")
                k = M.line_progress(t, t0 - 0.5)
                if k > 0 and xo < 1:
                    a = (1 - xo) * vd
                    x0, x1 = prev, x
                    d.line((x0, cy, x0 + (x1 - x0) * k, cy), fill=C("accent", int(200 * a)), width=max(1, int(2.5 * z)))
                    if k >= 1:
                        d.ellipse((x1 - 7 * z, cy - 7 * z, x1 + 7 * z, cy + 7 * z), fill=C("bg"), outline=C("accent", int(255 * a)), width=int(3 * z))
                        for u, al in M.running_dot(t, t0 - 0.5 + M.fr(M.F_LINE)):
                            px = x0 + (x1 - x0) * u
                            d.ellipse((px - 6 * z, cy - 6 * z, px + 6 * z, cy + 6 * z), fill=C("accent", int(255 * al * a)))
            self.card(img, t, spr, x, y, t0, act, br * vd, "right", name="flow", ph=i, T=T, ring=ring)
            prev = x + spr.width
            x += spr.width + self.gap


@template("lab_diagram",
          doc="lab · Center Diagram: одна схема по центру (узел с иконкой и подписью), ярлыки вокруг, линии от центра; "
              "эффект, механизм.",
          params={"center": {"icon": "flask", "title": "Habit loop", "at": 0},
                  "labels": [{"text": "cue", "at": 1}], **LabTemplate.COMMON},
          beats="центр — по center.at, ярлык i — по своему `at`")
class LabDiagram(LabTemplate):
    def plan_body(self):
        c = self.p.get("center") or {}
        self.c_t = self.at(c.get("at"), 0.4)
        self.lb = self.p.get("labels") or []
        self.lt = self.seq_times(self.lb, self.c_t + 0.6)
        self.fl = _focus_list([self.c_t] + self.lt, self.v_t or self.exit_t)

    def sfx_body(self):
        return [(self.c_t, "pop")] + [(x, "pop") for x in self.lt]

    def setup_body(self):
        z = self.z
        c = self.p.get("center") or {}
        R = int(150 * z)
        im, d = _ss_canvas(2 * R, 2 * R)
        d.ellipse((SS, SS, 2 * R * SS - SS, 2 * R * SS - SS), fill=C("bg2", 210), outline=C("accent", 90), width=2 * SS)
        node = _down(im, 2 * R, 2 * R)
        ic = line_icon(c.get("icon", "flask"), int(84 * z), "accent")
        node.alpha_composite(ic, (R - ic.width // 2, int(R - ic.height * 0.85)))
        tt = G.text_sprite(str(c.get("title", "")).upper(), int(28 * z), "extrabold", "text", family="head", maxw=int(2 * R - 40 * z))
        node.alpha_composite(tt, (R - tt.width // 2, int(R + 14 * z)))
        self.node, self.node_ring = node, ring_pad(2 * R, 2 * R, R)
        self.lab_spr = []
        for l in self.lb:
            t = G.text_sprite(l.get("text", ""), int(30 * z), "bold", "text", family="head", maxw=int(420 * z))
            w, h = int(t.width + 48 * z), int(t.height + 30 * z)
            card = glass(w, h, int(14 * z)).copy()
            card.alpha_composite(t, (int(24 * z), int(15 * z)))
            self.lab_spr.append((card, ring_pad(w, h, int(14 * z))))

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        cx, cy = self.W / 2, self.H * 0.47
        n = max(1, len(self.lb))
        d = ImageDraw.Draw(img, "RGBA")
        for i, ((spr, ring), t0) in enumerate(zip(self.lab_spr, self.lt)):
            ang = -math.pi / 2 + (i + 0.5) * math.tau / n if n > 2 else (math.pi if i == 0 else 0)
            rx, ry = 520 * z, 300 * z
            lx, ly = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
            k = M.line_progress(t, t0 - 0.35)
            xo = self.gone(t, "diagram")
            if k > 0:
                sx, sy = cx + 150 * z * math.cos(ang), cy + 150 * z * math.sin(ang)
                d.line((sx, sy, sx + (lx - sx) * k, sy + (ly - sy) * k), fill=C("accent", int(170 * vd * (1 - xo))), width=max(1, int(2.5 * z)))
                for u, al in (M.running_dot(t, t0 - 0.35 + M.fr(M.F_LINE)) if k >= 1 else []):
                    px, py = sx + (lx - sx) * u, sy + (ly - sy) * u
                    d.ellipse((px - 5 * z, py - 5 * z, px + 5 * z, py + 5 * z), fill=C("accent", int(255 * al * vd * (1 - xo))))
            br, act = foc.get(t0, (1, 0))
            self.card(img, t, spr, lx - spr.width / 2, ly - spr.height / 2, t0, act, br * vd, name="diagram", ph=i, T=T, ring=ring)
        br, act = foc.get(self.c_t, (1, 0))
        self.card(img, t, self.node, cx - self.node.width / 2, cy - self.node.height / 2, self.c_t, act, br * vd, name="diagram",
                  ph=0.3, T=T, ring=self.node_ring)


@template("lab_chapter",
          doc="lab · Карточка главы: «световой веер» 6 кадров → «01» в контуре + черта + заголовок капсом + подзаголовок "
              "моно + прогресс точками «chapter 1 of 8». Держать ≥ 2,5 с (min_duration). Между главами.",
          params={"number": 1, "total": 8, "title": "Wake up", "subtitle": "07:00 · facts 1–10", **LabTemplate.COMMON},
          beats="появляется сразу")
class LabChapter(LabTemplate):
    def sfx_body(self):
        return [(0.0, "whoosh"), (0.25, "pop")]

    def setup_body(self):
        z = self.z
        p = self.p
        n = int(p.get("number", 1))
        f = G.font(int(260 * z), "extrabold", "num")
        s = f"{n:02d}"
        bb = f.getbbox(s, stroke_width=int(4 * z))
        num = Image.new("RGBA", (bb[2] + int(10 * z), bb[3] + int(10 * z)), (0, 0, 0, 0))
        ImageDraw.Draw(num).text((int(4 * z), 0), s, font=f, fill=(0, 0, 0, 0), stroke_width=int(4 * z), stroke_fill=C("accent"))
        self.num = G.glowify(num, "accent", 24 * z, 0.5)
        self.title = G.text_sprite(str(p.get("title", "")).upper(), int(64 * z), "extrabold", "text", family="head",
                                   align="left", maxw=int(900 * z))
        self.subt = txt(p["subtitle"], 24 * z, "medium", "dim", "mono") if p.get("subtitle") else None
        self.prog = txt(f"chapter {n} of {int(p.get('total', 8))}", 20 * z, "medium", "dim", "mono", 0.04)
        self.n, self.total = n, int(p.get("total", 8))

    def draw_body(self, img, t, T):
        z = self.z
        # световой веер 6 кадров
        fk = M.prog(t, 0.0, M.fr(6) * 2)
        if fk < 1:
            fan = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(fan, "RGBA")
            cx, cy = -100 * z, self.H / 2
            a = math.sin(fk * math.pi)
            for i in range(9):
                ang = (-0.5 + i / 8) * 1.1 + fk * 0.6
                d.polygon([(cx, cy), (cx + 2600 * z * math.cos(ang - 0.04), cy + 2600 * z * math.sin(ang - 0.04)),
                           (cx + 2600 * z * math.cos(ang + 0.04), cy + 2600 * z * math.sin(ang + 0.04))],
                          fill=C("accent", int(34 * a)))
            img.alpha_composite(fan.filter(ImageFilter.GaussianBlur(28 * z)))
        xo = self.gone(t, "chapter")
        cy = self.H * 0.45
        k1 = M.ease_out_expo(M.prog(t, 0.15, M.fr(M.F_APPEAR)))
        x = 240 * z
        put(img, self.num, x, cy - self.num.height / 2 + (1 - k1) * 24 * z + M.bob(T, 1) * z, k1 * (1 - xo), 0.96 + 0.04 * k1, (1 - k1) * 8)
        bx = x + self.num.width + 40 * z
        lk = M.line_progress(t, 0.3, 18)
        d = ImageDraw.Draw(img, "RGBA")
        if lk > 0:
            h = 220 * z * lk
            d.line((bx, cy - h / 2, bx, cy + h / 2), fill=C("accent", int(255 * (1 - xo))), width=max(1, int(3 * z)))
        tx = bx + 48 * z
        k2 = M.ease_out_expo(M.prog(t, 0.45, M.fr(M.F_APPEAR)))
        put(img, self.title, tx + (1 - k2) * 32 * z, cy - self.title.height + 6 * z, k2 * (1 - xo))
        if self.subt is not None:
            k3 = M.ease_out_expo(M.prog(t, 0.6, M.fr(M.F_APPEAR)))
            put(img, self.subt, tx + (1 - k3) * 32 * z, cy + 22 * z, k3 * (1 - xo))
        k4 = M.ease_out_expo(M.prog(t, 0.8, M.fr(M.F_APPEAR))) * (1 - xo)
        if k4 > 0:
            y = self.H - 200 * z
            x0 = self.W / 2 - (self.total * 26 * z) / 2
            for i in range(self.total):
                c = C("accent", int(255 * k4)) if i < self.n else (255, 255, 255, int(50 * k4))
                r = (6 if i == self.n - 1 else 4.5) * z
                d.ellipse((x0 + i * 26 * z - r, y - r, x0 + i * 26 * z + r, y + r), fill=c)
            put(img, self.prog, self.W / 2, y + 34 * z, k4, anchor="c")
