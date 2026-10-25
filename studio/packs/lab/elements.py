"""Пакет lab: примитивы рисования (суперсэмплинг, стекло, текст, линейные иконки) и фирменные элементы §8
(штамп вердикта, карточка исследования, «Нейрон», часы дня)."""
from __future__ import annotations

import functools
import math
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ... import gfx as G

VERDICTS = {"TRUE": "true", "HALF-TRUE": "half", "MYTH": "myth", "NO EVIDENCE": "noev"}
SS = 3  # суперсэмплинг для векторных фигур


def C(name, a=255):
    return G.col(name, a)


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
    elif name == "wheel":  # колесо фортуны: обод, спицы, флажок-указатель сверху
        d.ellipse((m, m * 1.4, s - m, s - m * 0.6), outline=c, width=w)
        cx, cy, r = s / 2, s / 2 + m * 0.4, s / 2 - m
        for i in range(4):
            a = i * math.pi / 4
            d.line((cx - r * math.cos(a), cy - r * math.sin(a), cx + r * math.cos(a), cy + r * math.sin(a)), fill=c, width=w)
        d.polygon([(cx - s * .07, m * 0.2), (cx + s * .07, m * 0.2), (cx, m * 1.6)], fill=c)
    elif name == "house":
        d.line((m, s * .48, s / 2, m), fill=c, width=w)
        d.line((s / 2, m, s - m, s * .48), fill=c, width=w)
        d.line((s * .26, s * .4, s * .26, s - m), fill=c, width=w)
        d.line((s * .74, s * .4, s * .74, s - m), fill=c, width=w)
        d.line((s * .26, s - m, s * .74, s - m), fill=c, width=w)
        d.rectangle((s * .43, s * .6, s * .57, s - m), outline=c, width=w)
    elif name == "timer":  # секундомер
        d.ellipse((m, m * 1.6, s - m, s - m * 0.4), outline=c, width=w)
        d.line((s * .42, m * 0.6, s * .58, m * 0.6), fill=c, width=w)
        d.line((s / 2, m * 0.6, s / 2, m * 1.6), fill=c, width=w)
        d.line((s / 2, s * .56, s * .66, s * .42), fill=c, width=w)
    elif name == "anchor":
        d.ellipse((s * .42, m * 0.6, s * .58, m * 1.5), outline=c, width=w)
        d.line((s / 2, m * 1.5, s / 2, s - m), fill=c, width=w)
        d.line((s * .32, s * .36, s * .68, s * .36), fill=c, width=w)
        d.arc((m, s * .38, s - m, s - m), 20, 160, fill=c, width=w)
    elif name == "receipt":
        d.line((s * .28, m, s * .72, m), fill=c, width=w)
        d.line((s * .28, m, s * .28, s - m), fill=c, width=w)
        d.line((s * .72, m, s * .72, s - m), fill=c, width=w)
        for i in range(4):
            x0 = s * .28 + i * s * .11
            d.line((x0, s - m, x0 + s * .055, s - m - s * .06), fill=c, width=w)
            d.line((x0 + s * .055, s - m - s * .06, x0 + s * .11, s - m), fill=c, width=w)
        for y in (.34, .48, .62):
            d.line((s * .38, s * y, s * .62, s * y), fill=c, width=w)
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
def stamp_sprite(verdict, z=1.0, word=None):
    """Штамп вердикта: скруглённая плашка, обводка цвета вердикта, капс Unbounded, «чернильная» текстура."""
    c = VERDICTS.get(verdict.upper(), "myth")
    word = txt((word or verdict).upper(), 170 * z, "extrabold", c, "num", 0.04)  # слово — на языке ролика (D3)
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
def study_card(authors, where, evidence, z=1.0, w=724, labels=("STUDY", "EVIDENCE")):
    """Карточка исследования: STUDY · сила доказательств (5 сегментов) · авторы · журнал, год, n."""
    w = int(w * z)
    tag = txt(labels[0], 19 * z, "medium", "bg", "mono", 0.06)
    who = G.text_sprite(authors, int(30 * z), "extrabold", "text", family="head", align="left", maxw=int(w - 56 * z))
    whr = txt(where, 19 * z, "medium", "dim", "mono")
    h = int(24 * z + tag.height + 14 * z + who.height + 6 * z + whr.height + 24 * z)
    card = glass(w, h, int(18 * z)).copy()
    d = ImageDraw.Draw(card, "RGBA")
    x0, y0 = int(28 * z), int(24 * z)
    d.rounded_rectangle((x0, y0, x0 + tag.width + 10 * z, y0 + tag.height + 4 * z), 8 * z, fill=C("accent"))
    card.alpha_composite(tag, (x0 + int(3 * z), y0 + int(2 * z)))
    lab = txt(labels[1], 16 * z, "medium", "dim", "mono")
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


def _focus_list(times, end):
    """Фокус: элемент i активен от своего времени до времени следующего."""
    out = []
    for i, t0 in enumerate(times):
        t1 = times[i + 1] if i + 1 < len(times) else end
        out.append((t0, t1))
    return out
