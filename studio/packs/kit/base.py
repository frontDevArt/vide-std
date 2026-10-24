"""Пакет kit: база общих шаблонов библиотеки (ROADMAP C4) — триггеры `at`, заголовок, место блока в рабочей зоне.

Шаблоны kit не привязаны к палитре: цвета — имена палитры (`accent`, `accent2`, `text`, `dim`, `panel`) или #RRGGBB,
всё свёрстано в `self.area` (зона площадки без полосы субтитров) в любом формате кадра.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ... import assets as AS
from ... import gfx as G
from ... import media as MD
from ...gfx import blitc, eo, lerp, prog
from ..base import Box, Template
from ..lab.triggers import SECONDS, word_time
from ..registry import P

SS = 3  # суперсэмплинг векторных фигур


class KitTemplate(Template):
    """Триггер `at`: бит (int) | секунды (float, '1.5s') | слово озвучки ('word', 'w:two words#2') — как у media и lab.
    Элементы списка без `at` — по битам `first_beat + i`, иначе равномерно по сцене."""
    word_triggers = True  # validate и voice проверяют слова-триггеры `at` (packs/lab/check.py)
    COMMON = {"title": P(None, "заголовок над содержимым, *слово* — акцент", str),
              "color": P("accent", "цвет акцента: имя цвета палитры или #RRGGBB")}

    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        self.words = scene.get("words") or []
        self.roots = ctx.get("roots") or ["."]
        self.c = self.p.get("color") or "accent"
        self.kz = self.k if not self.vert else (1.15 if self.H > self.W * 1.2 else 1.0)
        self.ttl = None

    # ---------- размеры и время
    def fs(self, px):
        """Кегль: дизайн-пиксели 1080 по короткой стороне; в широком кадре крупнее (self.k), в высоком (9:16, 4:5) —
        тоже: телефон смотрят с руки, а места по высоте там больше, чем в квадрате."""
        return max(8, int(px * self.u * self.kz))

    def at(self, spec, default=0.0):
        if spec is None or isinstance(spec, bool):
            return default
        if isinstance(spec, int):
            return max(0.0, self.bt(spec, default) - 0.1) if -len(self.beats) <= spec < len(self.beats) else default
        if isinstance(spec, float):
            return spec
        m = SECONDS.fullmatch(str(spec).strip())
        if m:
            return float(m.group(1))
        t, _ = word_time(self.words, spec)
        return max(0.0, t - 0.1) if t is not None else default

    def item_at(self, item, i, n, start=0.35):
        """Время i-го из n элементов: item.at → бит first_beat + i → равномерно от start до ~2/3 сцены."""
        if isinstance(item, dict) and item.get("at") is not None:
            return self.at(item["at"], start)
        fb = self.p.get("first_beat")
        if fb is not None and -len(self.beats) <= int(fb) + i < len(self.beats):
            return max(0.0, self.bt(int(fb) + i) - 0.1)
        end = max(start + 0.3, self.D * 0.62)
        return lerp(start, end, i / (n - 1)) if n > 1 else start

    def fade(self, t):
        """Альфа выхода: последняя сцена держится до конца."""
        return 1.0 if self.last else 1 - prog(t, self.D - 0.35, self.D)

    # ---------- заголовок и место блока
    def setup_title(self, size=68):
        t = self.p.get("title")
        self.ttl = (G.text_sprite(t, self.fs(size), "black", "text", accent=self.c, maxw=int(self.area.w * 0.94))
                    if t else None)
        self.gap = int(36 * self.u) if self.ttl is not None else 0

    def room(self):
        """Высота под содержимое: рабочая зона минус заголовок."""
        return self.area.h - (self.ttl.height + self.gap if self.ttl is not None else 0)

    def place(self, body_h):
        """Блок «заголовок + содержимое высотой body_h» по центру рабочей зоны → Box содержимого."""
        a = self.area
        th = self.ttl.height + self.gap if self.ttl is not None else 0
        top = a.y0 + max(0.0, (a.h - th - body_h) / 2)
        self.ttl_y = top + (self.ttl.height / 2 if self.ttl is not None else 0)
        return Box(a.x0, top + th, a.x1, top + th + body_h)

    def draw_title(self, img, t, a=1.0, t0=0.0):
        if self.ttl is None:
            return
        k = eo(prog(t, t0, t0 + 0.45))
        blitc(img, self.ttl, self.area.cx, self.ttl_y + (1 - k) * 24 * self.u, a * k)

    # ---------- файлы проекта (фото автора, фон)
    def image(self, rel):
        return MD.image(AS.path(self.roots, rel)) if rel else None


# ------------------------------------------------------------------ общие рисунки
class Ink:
    """Фигуры с прозрачностью поверх кадра: `with Ink(img) as d: d.line(…)`. ImageDraw на RGBA-кадре не смешивает
    цвет, а записывает альфу в пиксели (в итоговом RGB полупрозрачное стало бы сплошным), поэтому фигуры рисуются на
    прозрачном слое и кладутся alpha_composite при выходе из блока — до спрайтов, которые должны лечь сверху."""

    def __init__(self, img):
        self.img = img
        self.layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    def __enter__(self):
        return ImageDraw.Draw(self.layer)

    def __exit__(self, *exc):
        self.img.alpha_composite(self.layer)


def circle(d, color, fill=None, outline=None, width=0):
    """Круг диаметра d (суперсэмплинг): заливка и/или обводка."""
    s = d * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((width * SS // 2, width * SS // 2, s - 1 - width * SS // 2, s - 1 - width * SS // 2),
                                fill=fill, outline=outline, width=width * SS)
    return img.resize((d, d), Image.LANCZOS)


def avatar(photo, d, initials, color, style):
    """Круглый аватар: фото (cover) или инициалы на круге цвета color."""
    m = Image.new("L", (d * SS, d * SS), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d * SS - 1, d * SS - 1), fill=255)
    m = m.resize((d, d), Image.LANCZOS)
    if photo is not None:
        img = MD.cover(photo.convert("RGBA"), d, d)
        img.putalpha(m)
        return img
    img = Image.new("RGBA", (d, d), style.col(color))
    img.putalpha(m)
    tx = G.text_sprite(initials, int(d * 0.4), "black", "bg_top", style=style)
    img.alpha_composite(tx, ((d - tx.width) // 2, (d - tx.height) // 2))
    return img


def initials(name):
    parts = [p for p in str(name or "").replace("-", " ").split() if p[:1].isalpha()]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


def star(d, color, fill=1.0, style=None):
    """Звезда диаметра d: fill — доля залитой ширины (0 — контур, 0,5 — половина)."""
    s = d * SS
    pts = []
    for i in range(10):
        r = s * (0.48 if i % 2 == 0 else 0.2)
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((s / 2 + r * math.cos(a), s / 2 + r * math.sin(a) + s * 0.03))
    base = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(base).polygon(pts, outline=G.col(color, 200, style), width=max(SS, int(s * 0.05)))
    if fill > 0:
        full = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ImageDraw.Draw(full).polygon(pts, fill=G.col(color, 255, style))
        base.alpha_composite(full.crop((0, 0, int(s * min(1.0, fill)), s)), (0, 0))
    return base.resize((d, d), Image.LANCZOS)


def number(v, decimals=0, prefix="", suffix=""):
    """1234.5 → '1,234.5'; разделители тысяч — с 1000 (как commerce.number)."""
    s = f"{v:,.{max(0, int(decimals))}f}" if abs(v) >= 1000 else f"{v:.{max(0, int(decimals))}f}"
    return f"{prefix}{s}{suffix}"
