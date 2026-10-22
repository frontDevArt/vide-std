"""Пакет commerce: спрайты и геометрия — ценник-бирка, чек, цепь, поворот, разделители тысяч.

Вынесено из projects/fake-discounts/templates/money.py (P2.9) без изменений рисования. Координаты бирки — дизайн-пиксели
при scale 1, итоговый масштаб — аргумент z (как self.z у шаблонов lab).
"""
from __future__ import annotations

import functools
import math
import re

from PIL import ImageDraw

from ... import gfx as G
from ..lab.elements import C, SS, _down, _ss_canvas, txt

TAG_W, TAG_H, HOLE_Y = 360, 440, 46     # бирка в дизайн-пикселях при scale 1


def thousands(s):
    """Числа от 1000 в строке — с запятыми: «$14550» → «$14,550»."""
    return re.sub(r"\d{4,}", lambda m: f"{int(m.group(0)):,}", s)


def rot(vx, vy, deg):
    """Поворот вектора экранных координат на deg против часовой (как Image.rotate)."""
    a = math.radians(deg)
    return vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)


@functools.lru_cache(maxsize=16)
def tag_parts(was, now, z, was_label="WAS", now_label="NOW"):
    """Корпус бирки (стекло, скошенный верх, люверс) + «WAS $199»; отдельно «NOW» и «$99» — они выпрыгивают.
    -> (корпус, (x0, x1, y) линии зачёркивания старой цены, спрайт «NOW», спрайт новой цены)."""
    w, h = int(TAG_W * z), int(TAG_H * z)
    img, d = _ss_canvas(w, h)
    k = SS * z
    pts = [(70, 0), (290, 0), (360, 70), (360, 422), (342, 440), (18, 440), (0, 422), (0, 70)]
    d.polygon([(x * k, y * k) for x, y in pts], fill=C("bg2", 245))
    d.line([(x * k, y * k) for x, y in pts + [pts[0]]], fill=(255, 255, 255, 52), width=int(2 * k), joint="curve")
    ins = [(76, 15), (284, 15), (345, 76), (345, 414), (334, 425), (26, 425), (15, 414), (15, 76)]
    d.line([(x * k, y * k) for x, y in ins + [ins[0]]], fill=C("accent2", 70), width=int(1.5 * k), joint="curve")
    d.ellipse(((180 - 24) * k, (HOLE_Y - 24) * k, (180 + 24) * k, (HOLE_Y + 24) * k), fill=C("dim", 200))
    body = _down(img, w, h)
    a = body.getchannel("A")
    ImageDraw.Draw(a).ellipse(((180 - 13) * z, (HOLE_Y - 13) * z, (180 + 13) * z, (HOLE_Y + 13) * z), fill=0)
    body.putalpha(a)
    lab = txt(was_label, 22 * z, "medium", "dim", "mono", 0.14)
    body.alpha_composite(lab, (int(w / 2 - lab.width / 2), int(96 * z)))
    pr = G.text_sprite(was, int(88 * z), "extrabold", "text", family="num")
    py = int(128 * z)
    body.alpha_composite(pr, (int(w / 2 - pr.width / 2), py))
    f = G.font(int(88 * z), "extrabold", "num")
    l, t, r, b = f.getbbox(was)
    iw = r - l
    strike = (w / 2 - iw / 2 - 14 * z, w / 2 + iw / 2 + 14 * z, py + (t + b) * 0.52)
    nlab = txt(now_label, 22 * z, "medium", "dim", "mono", 0.14)
    npr = G.glowify(G.text_sprite(now, int(116 * z), "extrabold", "accent", family="num"), "accent", 22 * z, 0.45)
    return body, strike, nlab, npr


def chain(d, p0, p1, sag, z, alpha, color="dim"):
    """Цепь: кружки-звенья через одно с короткими штрихами, по квадратичной кривой с провисом sag (px вниз)."""
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 2 or alpha <= 0.01:
        return
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2 + sag
    n = max(2, int(L / (11 * z)))
    pts = []
    for i in range(n + 1):
        u = i / n
        pts.append(((1 - u) ** 2 * x0 + 2 * u * (1 - u) * mx + u * u * x1, (1 - u) ** 2 * y0 + 2 * u * (1 - u) * my + u * u * y1))
    col = C(color, int(235 * alpha))
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        if i % 2 == 0:
            r = 5.2 * z
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=max(1, int(2.4 * z)))
        else:
            d.line((ax, ay, bx, by), fill=col, width=max(1, int(3 * z)))


def receipt_paper(lines, hl, torn, z, title, w=340, lh=40):
    """Бумага чека: шапка title, строки (новая — сверху, у щели принтера), зубчатый низ. lines — tuple, новые первыми.
    hl — первая строка подсвечена; torn — оторван: верхний край тоже зубчатый; строка без «|» — итог крупнее по центру,
    без отточия. w, lh — ширина и высота строки в дизайн-пикселях."""
    w, lh = int(w * z), lh * z
    head = 64 * z
    h = int(head + lh * len(lines) + 34 * z)
    img, d = _ss_canvas(w, h)
    k = SS
    teeth = 12 * z
    n = int(w / (2 * teeth))
    if torn:
        poly = []
        for i in range(n + 1):
            poly.append((i * 2 * teeth * k, teeth * k))
            if i < n:
                poly.append((i * 2 * teeth * k + teeth * k, 0))
        poly += [(w * k, teeth * k), (w * k, (h - teeth) * k)]
    else:
        poly = [(0, 0), (w * k, 0), (w * k, (h - teeth) * k)]
    for i in range(n, -1, -1):
        poly.append((i * 2 * teeth * k + teeth * k, h * k if i < n else (h - teeth) * k))
        poly.append((i * 2 * teeth * k, (h - teeth) * k))
    d.polygon(poly, fill=(30, 38, 58, 240))
    paper = _down(img, w, h)
    dd = ImageDraw.Draw(paper, "RGBA")
    f = G.font(int(19 * z), "medium", "mono")
    y = 18 * z
    dd.text((22 * z, y), title, font=f, fill=C("dim"))
    y = head - 10 * z
    for x in range(int(22 * z), int(w - 22 * z), int(12 * z)):
        dd.line((x, y, x + 6 * z, y), fill=(255, 255, 255, 50), width=max(1, int(1.5 * z)))
    y = head
    for i, ln in enumerate(lines):
        left, bar, right = ln.partition("|")
        col = C("accent") if (i == 0 and hl) else C("text", 225)
        if not bar:
            fb = G.font(int(21 * z), "bold", "mono")
            dd.text((w / 2 - fb.getlength(left) / 2, y + 5 * z), left, font=fb, fill=C("accent2") if i == 0 else col)
            y += lh
            continue
        dd.text((22 * z, y + 6 * z), left, font=f, fill=col)
        rw = f.getlength(right)
        dd.text((w - 22 * z - rw, y + 6 * z), right, font=f, fill=col)
        lw = f.getlength(left)
        x = 22 * z + lw + 10 * z
        while x < w - 22 * z - rw - 12 * z:
            dd.ellipse((x, y + 22 * z, x + 2.4 * z, y + 24.4 * z), fill=C("dim", 160))
            x += 9 * z
        y += lh
    return paper
