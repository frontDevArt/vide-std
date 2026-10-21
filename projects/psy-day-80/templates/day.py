"""Шаблоны ролика «Мозг на автопилоте»: часы дня в углу (во всех сценах), номер факта, проверка мифа.

Время на часах — функция главы (CLOCK), поэтому через склейки сцен оно непрерывно без state:
на титре остановки (`day_stop`) стрелки докручиваются от времени прошлой главы к новой.
"""
from __future__ import annotations

import math
import re

from PIL import Image, ImageDraw

from studio import gfx as G
from studio import templates as TP
from studio.gfx import blit, blitc, col, eio, eo, eob, lerp, prog
from studio.templates import Template, template

# глава -> (время, название остановки)
CLOCK = {
    "ch00": ("06:59", "Перед будильником"),
    "ch01": ("07:00", "Подъём"),
    "ch02": ("08:10", "Дорога"),
    "ch03": ("10:00", "Совещание"),
    "ch04": ("13:00", "Обед"),
    "ch05": ("18:20", "У зеркала"),
    "ch06": ("19:30", "Ужин с друзьями"),
    "ch07": ("21:15", "Диван и телефон"),
    "ch08": ("23:00", "Отбой"),
    "ch09": ("23:59", "Итоги дня"),
}
ORDER = list(CLOCK)
DAY0, DAY1 = 7 * 60 - 10, 24 * 60  # шкала таймлайна: 06:50 → 24:00


def _mins(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _fmt(m):
    m = int(round(m)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def chapter_clock(ch):
    return CLOCK.get(ch, ("07:00", ""))


def prev_clock(ch):
    i = ORDER.index(ch) if ch in ORDER else 0
    return CLOCK[ORDER[max(0, i - 1)]]


# ============================================================== HUD
class Hud:
    """Циферблат + время + остановка + таймлайн дня. Статичные части — спрайты, стрелки — каждый кадр."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        u = self.u = min(W, H) / 1080
        self.R = int(56 * u)
        S = self.R * 2 + int(8 * u)
        dial = Image.new("RGBA", (S * 3, S * 3), (0, 0, 0, 0))
        d = ImageDraw.Draw(dial)
        c = S * 3 / 2
        r = self.R * 3
        d.ellipse((c - r, c - r, c + r, c + r), fill=col("panel", 235), outline=col("accent"), width=int(9 * u))
        for i in range(12):
            a = i / 12 * math.tau
            r0 = r * (0.78 if i % 3 == 0 else 0.86)
            d.line((c + math.sin(a) * r0, c - math.cos(a) * r0, c + math.sin(a) * r * 0.93, c - math.cos(a) * r * 0.93),
                   fill=col("dim"), width=int(7 * u))
        self.dial = G.glowify(dial.resize((S, S), Image.LANCZOS), "accent", 10 * u, 0.6)
        self.cx, self.cy = W - 92 * u, 92 * u
        self.x0, self.x1, self.ty = W - 560 * u, W - 36 * u, 186 * u
        track = Image.new("RGBA", (int(self.x1 - self.x0), int(6 * u)), col("dim", 90))
        self.track = track
        self.ticks = []
        for ch in ORDER[1:-1]:
            self.ticks.append(self.tx(_mins(CLOCK[ch][0])))

    def tx(self, m):
        return lerp(self.x0, self.x1, G.clamp((m - DAY0) / (DAY1 - DAY0)))

    def draw(self, img, minutes, name, alpha=1.0, name_alpha=1.0):
        if alpha <= 0.01:
            return
        u = self.u
        blitc(img, self.dial, self.cx, self.cy, alpha)
        hands = Image.new("RGBA", (self.R * 6, self.R * 6), (0, 0, 0, 0))
        d = ImageDraw.Draw(hands)
        c = self.R * 3
        hm = (minutes / 60) % 12
        for ang, ln, w, cc in ((hm / 12 * math.tau, 0.5, 13, "text"), ((minutes % 60) / 60 * math.tau, 0.78, 9, "accent")):
            d.line((c, c, c + math.sin(ang) * self.R * 3 * ln, c - math.cos(ang) * self.R * 3 * ln), fill=col(cc), width=int(w * u))
        d.ellipse((c - 14 * u, c - 14 * u, c + 14 * u, c + 14 * u), fill=col("accent2"))
        blitc(img, hands.resize((self.R * 2, self.R * 2), Image.LANCZOS), self.cx, self.cy, alpha)
        tm = G.text_sprite(_fmt(minutes), int(50 * u), "black", "text")
        blit(img, tm, self.cx - self.R - 18 * u - tm.width, self.cy - 50 * u, alpha)
        if name:
            nm = G.text_sprite(name, int(26 * u), "semibold", "dim")
            blit(img, nm, self.cx - self.R - 18 * u - nm.width, self.cy + 8 * u, alpha * name_alpha)
        # таймлайн дня
        blit(img, self.track, self.x0, self.ty - 3 * u, alpha)
        xm = self.tx(minutes)
        if xm - self.x0 > 2:
            blit(img, Image.new("RGBA", (int(xm - self.x0), int(6 * u)), col("accent", 230)), self.x0, self.ty - 3 * u, alpha)
        for x in self.ticks:
            on = x <= xm + 1
            dot = G.rrect((int(10 * u), int(10 * u)), int(5 * u), col("accent" if on else "dim", 255 if on else 140))
            blitc(img, dot, x, self.ty, alpha)
        blitc(img, G.radial(int(46 * u), "accent2", 0.9), xm, self.ty, alpha)
        blitc(img, G.rrect((int(14 * u), int(14 * u)), int(7 * u), col("accent2")), xm, self.ty, alpha)


_HUD = {}


def hud(W, H):
    if (W, H) not in _HUD:
        _HUD[(W, H)] = Hud(W, H)
    return _HUD[(W, H)]


class DayMixin:
    """Рисует HUD поверх сцены. Время = глава; на `day_stop` — докрутка от прошлой остановки."""
    spin = None  # (t0, t1) докрутки стрелок

    def hud_draw(self, img, t):
        ch = self.s["chapter"]
        now, name = chapter_clock(ch)
        m1 = _mins(now)
        a = G.eo(prog(t, 0, 0.6)) if self.first else 1.0
        if self.spin:
            m0 = _mins(prev_clock(ch)[0])
            if m1 < m0:
                m1 += 24 * 60
            k = eio(prog(t, *self.spin))
            pname = prev_clock(ch)[1]
            hud(self.W, self.H).draw(img, lerp(m0, m1, k), name if k > 0.5 else pname, a,
                                     abs(k - 0.5) * 2 if 0 < k < 1 else 1.0)
        else:
            hud(self.W, self.H).draw(img, m1, name, a)


def with_hud(base, name):
    cls = type("Day" + base.__name__, (DayMixin, base), {})
    orig = base.draw

    def draw(self, img, t, T):
        orig(self, img, t, T)
        self.hud_draw(img, t)

    cls.draw = draw
    template(name, doc=base.DOC + " (+часы дня)", params=base.PARAMS, beats=base.BEATS)(cls)
    return cls


for _n in ("title", "statement", "bullets", "counter", "outro"):
    with_hud(TP.REGISTRY[_n], "day_" + _n)


# ============================================================== day_stop
@template("day_stop", doc="Титр остановки дня: крупное время, название, «факты N–M»; часы в углу докручиваются.",
          params={"facts": "факты 1–10", "title": None, "facts_beat": 1},
          beats="время и название — сразу, подпись — с битом facts_beat")
class DayStop(DayMixin, Template):
    def setup(self):
        u, k = self.u, self.k
        now, name = chapter_clock(self.s["chapter"])
        self.now, self.prev = now, prev_clock(self.s["chapter"])[0]
        self.spin = (0.15, 1.5)
        self.title = G.text_sprite(self.p.get("title") or name, int(96 * u * k), "black", "text", glow=int(18 * u),
                                   glow_color="accent", maxw=int(self.W * 0.8))
        self.sub = G.text_sprite(self.p.get("facts", ""), int(44 * u * k), "semibold", "accent2")

    def draw(self, img, t, T):
        u = self.u
        a = self.io(t, 0.3, 0.45)
        m0, m1 = _mins(self.prev), _mins(self.now)
        if m1 < m0:
            m1 += 24 * 60
        kk = eio(prog(t, *self.spin))
        tm = G.text_sprite(_fmt(lerp(m0, m1, kk)), int(230 * u), "black", "accent", glow=int(28 * u), glow_color="accent")
        cy = self.H * 0.30
        blitc(img, tm, self.W / 2, cy, a, 1 + 0.04 * math.sin(kk * math.pi))
        k2 = prog(t, 1.0, 1.6)
        blitc(img, self.title, self.W / 2, self.H * 0.55 + (1 - eo(k2)) * 30 * u, eo(k2) * a)
        t3 = max(1.4, self.bt(int(self.p.get("facts_beat", 1)), 1.4) - 0.1)
        k3 = prog(t, t3, t3 + 0.5)
        blitc(img, self.sub, self.W / 2, self.H * 0.68, eo(k3) * a)
        self.hud_draw(img, t)


# ============================================================== day_fact / day_myth
VERDICT = {"no": ("НЕ ПОДТВЕРДИЛОСЬ", "red"), "partly": ("ЧАСТИЧНО", "amber"), "yes": ("ПОДТВЕРДИЛОСЬ", "lime")}


@template("day_fact", doc="Факт: номер крупно слева, справа суть + иконка, опц. крупное число, столбики-сравнение, "
                          "плашки-пункты; источник мелко под номером.",
          params={"n": 1, "title": "Суть *факта*", "icon": None, "title_beat": 0,
                  "value": None, "label": None, "value_beat": 1, "count": True,
                  "bars": None, "bars_beat": 1, "chips": None, "chips_beat": 1, "src": None},
          beats="title — title_beat; value/bars/chips — с их *_beat (столбик/плашка i — бит +i)")
class DayFact(DayMixin, Template):
    kicker, num_color = "ФАКТ", "accent"

    def _t(self, b, default):
        if b is None:
            return default
        return max(0.05, self.bt(int(b), default) - 0.1)

    def setup(self):
        u, k = self.u, self.k
        p = self.p
        self.ncx = self.W * 0.205
        if p.get("n") is None:  # без номера — колонка по центру
            self.rx0, self.rw = self.W * 0.17, self.W * 0.66
        else:
            self.rx0, self.rw = self.W * 0.40, self.W * 0.54
        self.rcx = self.rx0 + self.rw / 2
        n = p.get("n")
        self.num = (G.text_sprite(f"{int(n):02d}", int(300 * u), "black", self.num_color, glow=int(30 * u),
                                  glow_color=self.num_color) if n is not None else None)
        self.kk = G.text_sprite(p.get("kicker", self.kicker), int(34 * u), "bold", "dim")
        self.src = (G.text_sprite(p["src"], int(26 * u), "medium", "dim", maxw=int(self.W * 0.3))
                    if p.get("src") else None)
        blocks = []  # (kind, data, height, t_appear)
        self.head_blocks(blocks)
        if p.get("icon"):
            ic = G.icon(p["icon"], int(110 * u), p.get("color", "accent"))
            blocks.append(("spr", ic, ic.height * 0.8, self._t(p.get("title_beat", 0), 0.2)))
        if p.get("title"):
            tt = G.text_sprite(p["title"], int(60 * u * k), "black", "text", accent=p.get("color", "accent"),
                               maxw=int(self.rw))
            blocks.append(("spr", tt, tt.height, self._t(p.get("title_beat", 0), 0.2)))
        if p.get("value"):
            blocks.append(("value", None, 190 * u + (60 * u if p.get("label") else 0),
                           self._t(p.get("value_beat", 1), self.D * 0.35)))
            self.lbl = (G.text_sprite(p["label"], int(36 * u * k), "semibold", "dim", maxw=int(self.rw))
                        if p.get("label") else None)
        if p.get("bars"):
            self.bars = []
            mx = max(float(b["value"]) for b in p["bars"]) or 1
            fb = p.get("bars_beat", 1)
            for i, b in enumerate(p["bars"]):
                lb = G.text_sprite(b["label"], int(34 * u * k), "semibold", "text", align="left", maxw=int(self.rw * 0.42))
                vt = G.text_sprite(b.get("text", str(b["value"])), int(44 * u * k), "black", b.get("color", "accent"))
                self.bars.append((lb, vt, float(b["value"]) / mx, b.get("color", "accent"),
                                  self._t(fb + i if fb is not None else None, self.D * (0.3 + 0.15 * i))))
            blocks.append(("bars", None, len(self.bars) * 84 * u, min(b[4] for b in self.bars)))
        if p.get("chips"):
            self.chips = []
            fb = p.get("chips_beat", 1)
            for i, c in enumerate(p["chips"]):
                tx = G.text_sprite(c, int(36 * u * k), "semibold", "text", maxw=int(self.rw - 60 * u))
                pw, ph = tx.width + int(48 * u), tx.height + int(24 * u)
                pn = G.panel(pw, ph, int(ph * 0.3), border=p.get("color", "accent"), glow=int(6 * u), bw=2)
                pd = (pn.width - pw) // 2
                pn.alpha_composite(tx, (pd + (pw - tx.width) // 2, pd + (ph - tx.height) // 2))
                self.chips.append((pn, self._t(fb + i if fb is not None else None, self.D * (0.3 + 0.12 * i))))
            blocks.append(("chips", None, sum(c[0].height * 0.82 for c in self.chips), min(c[1] for c in self.chips)))
        top, bot = 235 * u, self.H * 0.80  # ниже таймлайна HUD, выше субтитров
        hs = sum(b[2] for b in blocks)
        gap = max(10 * u, min(34 * u, (bot - top - hs) / max(1, len(blocks) - 1)))
        total = hs + gap * (len(blocks) - 1)
        y = min(max(top, self.H * 0.50 - total / 2), max(top, bot - total))
        self.blocks = []
        for kind, data, h, t0 in blocks:
            self.blocks.append((kind, data, y + h / 2, h, t0))
            y += h + gap
        self.post_setup()

    def head_blocks(self, blocks):
        pass

    def post_setup(self):
        pass

    def _value_text(self, t, t0):
        v = str(self.p["value"])
        m = re.match(r"^([^\d]*)(\d+)(.*)$", v)
        if not m or not self.p.get("count", True):
            return v
        k = eio(prog(t, t0, t0 + 0.9))
        return f"{m.group(1)}{int(round(int(m.group(2)) * k))}{m.group(3)}"

    def draw(self, img, t, T):
        u = self.u
        a = self.io(t, 0.3, 0.35)
        # левая колонка: номер
        if self.num is not None:
            kn = prog(t, 0.0, 0.45)
            ny = self.H * 0.45
            blitc(img, self.kk, self.ncx, ny - self.num.height * 0.5 + 10 * u, eo(kn) * a)
            blitc(img, self.num, self.ncx, ny + (1 - eo(kn)) * 30 * u, eo(kn) * a, lerp(0.9, 1, eob(kn)))
            if self.src is not None:
                blitc(img, self.src, self.ncx, ny + self.num.height * 0.42 + 26 * u, eo(prog(t, 0.6, 1.1)) * a)
            line = G.rrect((int(4 * u), int(self.H * 0.42)), int(2 * u), col("dim", 90))
            blitc(img, line, self.W * 0.355, self.H * 0.47, a * eo(kn))
        # правая колонка
        for bi, (kind, data, cy, h, t0) in enumerate(self.blocks):
            k = prog(t, t0, t0 + 0.5)
            if k <= 0:
                continue
            if kind == "spr":
                blitc(img, data, self.rcx, cy + (1 - eo(k)) * 30 * u, eo(k) * a * self.block_alpha(bi, t))
            elif kind == "value":
                c = self.p.get("value_color", "accent2")
                vs = G.text_sprite(self._value_text(t, t0), int(170 * u), "black", c, glow=int(22 * u), glow_color=c)
                vy = cy - (30 * u if self.lbl else 0)
                blitc(img, vs, self.rcx, vy, eo(k) * a, lerp(0.85, 1, eob(k)))
                if self.lbl is not None:
                    blitc(img, self.lbl, self.rcx, vy + 95 * u + self.lbl.height / 2, eo(prog(t, t0 + 0.3, t0 + 0.8)) * a)
            elif kind == "bars":
                y = cy - h / 2 + 42 * u
                for lb, vt, frac, c, tb in self.bars:
                    kb = prog(t, tb, tb + 0.8)
                    if kb > 0:
                        blit(img, lb, self.rx0, y - lb.height / 2, eo(kb) * a)
                        bx = self.rx0 + self.rw * 0.44
                        bw = (self.rw * 0.56 - vt.width - 20 * u) * frac * eio(kb)
                        if bw > 2:
                            blit(img, G.rrect((int(bw), int(40 * u)), int(10 * u), col(c, 230)), bx, y - 20 * u, a)
                        blit(img, vt, bx + bw + 14 * u, y - vt.height / 2, eo(prog(t, tb + 0.4, tb + 0.9)) * a)
                    y += 84 * u
            elif kind == "chips":
                y = cy - h / 2
                for pn, tc in self.chips:
                    kc = prog(t, tc, tc + 0.45)
                    if kc > 0:
                        blitc(img, pn, self.rcx + (1 - eo(kc)) * 60 * u, y + pn.height * 0.41, eo(kc) * a)
                    y += pn.height * 0.82
        self.draw_extra(img, t, a)
        self.hud_draw(img, t)

    def draw_extra(self, img, t, a):
        pass

    def block_alpha(self, i, t):
        return 1.0


@template("day_myth", doc="Проверка мифа: плашка «ПРОВЕРКА МИФА», миф в кавычках, что нашли (value/bars/chips), "
                          "на бите verdict_beat — штамп (no | partly | yes, или verdict_text).",
          params={"n": 7, "myth": "«Привычка за 21 день»", "chip": "ПРОВЕРКА МИФА", "verdict": "no",
                  "verdict_text": None, "verdict_color": None, "verdict_beat": -1,
                  "value": None, "label": None, "value_beat": 1, "count": True, "bars": None, "bars_beat": 1,
                  "chips": None, "chips_beat": 1, "src": None},
          beats="плашка и миф — сразу; находки — по *_beat; штамп — verdict_beat")
class DayMyth(DayFact):
    kicker, num_color = "ФАКТ", "accent2"

    def head_blocks(self, blocks):
        u, k = self.u, self.k
        tx = G.text_sprite(self.p.get("chip", "ПРОВЕРКА МИФА"), int(34 * u), "black", "panel")
        pw, ph = tx.width + int(40 * u), tx.height + int(18 * u)
        chip = G.rrect((pw, ph), int(ph / 2), col("accent2"))
        chip.alpha_composite(tx, ((pw - tx.width) // 2, (ph - tx.height) // 2))
        blocks.append(("spr", chip, ph, 0.15))
        my = G.text_sprite(self.p.get("myth", ""), int(58 * u * k), "black", "text", accent="accent2", maxw=int(self.rw))
        blocks.append(("spr", my, my.height, 0.35))  # миф; после штампа гаснет (зачёркнут)
        self.myth_cy_idx = len(blocks) - 1

    def post_setup(self):
        u = self.u
        txt, c = VERDICT.get(self.p.get("verdict", "no"), VERDICT["no"])
        txt = self.p.get("verdict_text") or txt
        c = self.p.get("verdict_color") or c
        ts = G.text_sprite(txt, int(58 * u), "black", c, maxw=int(self.rw * 0.9))
        pw, ph = ts.width + int(60 * u), ts.height + int(34 * u)
        st = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(st)
        d.rounded_rectangle((3, 3, pw - 4, ph - 4), int(16 * u), fill=col("panel", 240), outline=col(c), width=int(7 * u))
        d.rounded_rectangle((int(14 * u), int(14 * u), pw - int(15 * u), ph - int(15 * u)), int(10 * u), outline=col(c, 150),
                            width=int(2 * u))
        st.alpha_composite(ts, ((pw - ts.width) // 2, (ph - ts.height) // 2))
        self.stamp = G.glowify(st, c, 12 * u, 0.7)
        vb = int(self.p.get("verdict_beat", -1))
        self.tv = max(0.3, self.bt(vb, self.D * 0.75) - 0.05)
        _, _, cy, h, _ = self.blocks[self.myth_cy_idx]
        self.stamp_cy = cy

    def block_alpha(self, i, t):
        if i == self.myth_cy_idx:
            return 1 - 0.65 * prog(t, self.tv, self.tv + 0.3)
        return 1.0

    def draw_extra(self, img, t, a):
        k = prog(t, self.tv, self.tv + 0.28)
        if k > 0:
            s = lerp(1.9, 1.0, eo(k))
            blitc(img, self.stamp, self.rcx, self.stamp_cy, min(1, k * 2) * a, s, -6)
