"""Пакет lab: шаблоны full_number, versus, flow, diagram, chapter."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from ... import gfx as G
from ... import motion as M
from ...lang import ui
from ..registry import AT, P, template
from .base import LabTemplate
from .elements import C, SS, _down, _focus_list, _ss_canvas, glass, line_icon, put, ring_pad, tile, txt

@template("full_number", aliases=("lab_full_number",),
          doc="lab · Full Number: одна цифра на весь кадр + подпись; опц. «миф → реальность» (myth: зачёркнутое "
              "мифическое значение, счётчик доматывает до реального). Разрыв ритма, шок-факт.",
          params={"value": P(66, "реальное значение"), "from": P(0, "с чего начинается счёт"),
                  "prefix": P("", "перед числом ($)"), "suffix": P("", "после числа (%)"), "caption": P("days", "подпись"),
                  "sub": P("", "вторая строка подписи"), "color": P("accent", "цвет цифры"),
                  "at": P(0, "старт счёта: бит, секунды или слово", AT),
                  "myth": P(None, "«миф → реальность» {value, strike_at}", dict), **LabTemplate.COMMON},
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
        self.fit = 1.0
        if not self.wide:  # высокий кадр: самое длинное значение — не шире рамки ($14,550 в 9:16, ROADMAP B3)
            vals = [p.get("value", 0), p.get("from", 0)] + ([p["myth"].get("value", 0)] if p.get("myth") else [])
            ink = max(G.text_sprite(self._str(v), int(320 * z), "extrabold", "accent", family="num").width
                      for v in vals)
            self.fit = min(1.0, self.area.w / ink)

    def _str(self, v):
        """Строка числа, как её рисует _spr (наследник может переписать — разделители тысяч)."""
        return f"{self.p.get('prefix', '')}{int(round(float(v)))}{self.p.get('suffix', '')}"

    def _spr(self, s, color):
        z = self.z
        spr = G.text_sprite(s, int(320 * z), "extrabold", color, family="num")
        return G.glowify(spr, color, 60 * z, 0.4)

    def draw_body(self, img, t, T):
        z = self.z
        p = self.p
        vd = self.vdim(t)
        my = p.get("myth")
        cx, cy = (self.W / 2, self.H * 0.44) if self.wide else (self.area.cx, self.area.y0 + self.area.h * 0.4)
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
        f = self.fit
        put(img, spr, cx, cy + (1 - k) * 24 * z + M.bob(T, 1) * z, a, (0.96 + 0.04 * k) * (1 + 0.02 * M.pulse(T) - 0.02) * f, (1 - k) * 8, anchor="c")
        if my and self.m_strike is not None:
            sk = M.ease_in_out(M.prog(t, self.m_strike, M.fr(M.F_FOCUS))) * (1 - M.prog(t, self.c_at, M.fr(4)))
            bw = int(spr.width * f * 0.7 * sk)
            if bw > 2:
                bar = G.glowify(G.rrect((bw, int(16 * z)), int(8 * z), C("myth")), "myth", 14 * z, 0.6)
                put(img, bar, cx - spr.width * f * 0.35, cy - 8 * z, a)
        y = cy + spr.height * f * 0.42
        if self.cap is not None:
            ck = M.ease_out_expo(M.prog(t, self.c_at + 0.25, M.fr(M.F_APPEAR)))
            cf = 1.0 if self.wide else min(1.0, self.area.w / self.cap.width)  # высокий кадр: подпись не шире рамки
            put(img, self.cap, cx, y + (1 - ck) * 16 * z, ck * a, cf, anchor="c")
        if self.sub is not None:
            sk = M.ease_out_expo(M.prog(t, self.c_at + 0.45, M.fr(M.F_APPEAR)))
            put(img, self.sub, cx, y + 56 * z, sk * a, anchor="c")


@template("versus", aliases=("lab_versus",),
          doc="lab · Versus: две колонки «Думают / Нашли», посередине разделитель; пункты — карточки по `at`. "
              "Для проверки мифа.",
          params={"left": P({"title": "THEY SAY", "items": [{"text": "21 days", "at": 0}]}, "колонка «думают» {title, items[{text, at}]}"),
                  "right": P({"title": "STUDIES FOUND", "items": [{"text": "66 days (median)", "at": 1}]},
                             "колонка «нашли» {title, items[{text, at}]}"),
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
        w = int(760 * z) if self.wide else int(self.area.w)
        tx = G.text_sprite(s, int(34 * z), "bold", "text", family="head", align="left", maxw=int(w - 80 * z))
        h = int(tx.height + 52 * z)
        card = glass(w, h, int(18 * z)).copy()
        d = ImageDraw.Draw(card)
        d.rounded_rectangle((int(22 * z), int(22 * z), int(28 * z), h - int(22 * z)), int(3 * z), fill=C(c))
        card.alpha_composite(tx, (int(48 * z), int(26 * z)))
        return card, ring_pad(w, h, int(18 * z), c)

    def draw_body(self, img, t, T):
        if not self.wide:
            return self._draw_tall(img, t, T)
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
            vs = txt(ui(self.ctx.get("language"), "vs"), 22 * z, "extrabold", "dim", "num")
            put(img, vs, x, 180 * z, dk * vd, anchor="c")

    def _draw_tall(self, img, t, T):
        """Высокий кадр: колонки друг под другом — «думают» сверху, разделитель «VS», «нашли» снизу."""
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        x, y = self.area.x0, self.top
        for side in (0, 1):
            if side == 1:  # разделитель с «VS» посередине
                dk = M.line_progress(t, 0.2, 27) * (1 - self.gone(t, "versus"))
                if dk > 0:
                    d = ImageDraw.Draw(img, "RGBA")
                    cy, half = y + 30 * z, self.area.w / 2 * dk
                    vs = txt(ui(self.ctx.get("language"), "vs"), 22 * z, "extrabold", "dim", "num")
                    gap = vs.width / 2 + 18 * z
                    for a, b in ((self.area.cx - half, self.area.cx - gap), (self.area.cx + gap, self.area.cx + half)):
                        if b > a:
                            d.line((a, cy, b, cy), fill=(255, 255, 255, int(40 * vd)), width=max(1, int(2 * z)))
                    put(img, vs, self.area.cx, cy, dk * vd, anchor="c")
                y += 80 * z
            k = M.appear(t, 0.3 + 0.12 * side, None)[0] * (1 - self.gone(t, "versus"))
            put(img, self.heads[side], x, y + M.bob(T, side) * z, k * vd)
            y += self.heads[side].height + 24 * z
            times = self.lt if side == 0 else self.rt
            for (spr, ring), t0 in zip(self.items[side], times):
                br, act = foc.get(t0, (1, 0))
                self.card(img, t, spr, x, y, t0, act, br * vd, "bottom" if side == 0 else "right", name="versus",
                          ph=side + y / 300, T=T, ring=ring)
                y += spr.height + 22 * z


@template("flow", aliases=("lab_flow",),
          doc="lab · Flow: 3 станции слева направо, соединены линиями с бегущими точками; процесс, «как это работает».",
          params={"stations": P([{"icon": "alarm", "title": "Cue", "sub": "same time, same place", "at": 0}],
                                "станции {icon, title, sub, at}"), **LabTemplate.COMMON},
          beats="станция i — по `at`; линия к ней рисуется перед её появлением")
class LabFlow(LabTemplate):
    def plan_body(self):
        self.st = self.p.get("stations") or []
        self.tt = self.seq_times(self.st, 0.5)
        self.fl = _focus_list(self.tt, self.v_t or self.exit_t)

    def sfx_body(self):
        return [(x, "pop") for x in self.tt]

    def setup_body(self):
        if not self.wide:
            return self._setup_tall()
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

    def _setup_tall(self):
        """Высокий кадр: станции — карточки во всю ширину рамки (плитка слева, текст справа), сверху вниз."""
        z = self.z
        w = int(self.area.w)
        self.spr = []
        for s in self.st:
            tl = tile(s.get("icon", "check"), int(72 * z))
            tw = int(w - 28 * z - tl.width - 24 * z - 24 * z)
            t1 = G.text_sprite(s.get("title", ""), int(36 * z), "extrabold", "text", family="head", align="left", maxw=tw)
            t2 = G.text_sprite(s["sub"], int(20 * z), "medium", "dim", family="mono", align="left", maxw=tw) if s.get("sub") else None
            th = t1.height + (8 * z + t2.height if t2 else 0)
            h = int(max(tl.height, th) + 56 * z)
            card = glass(w, h, int(18 * z)).copy()
            card.alpha_composite(tl, (int(28 * z), (h - tl.height) // 2))
            x, y = int(28 * z + tl.width + 24 * z), int((h - th) / 2)
            card.alpha_composite(t1, (x, y))
            if t2:
                card.alpha_composite(t2, (x, int(y + t1.height + 8 * z)))
            self.spr.append((card, ring_pad(w, h, int(18 * z))))
        self.gap = 90 * z

    def _draw_tall(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        d = ImageDraw.Draw(img, "RGBA")
        total = sum(s.height for s, _ in self.spr) + self.gap * (len(self.spr) - 1)
        y = max(self.top, self.top + (self.area.y1 - self.top - total) / 2 - 60 * z)
        lx = self.area.x0 + 28 * z + 36 * z  # линия — по оси плиток
        prev = None
        for i, ((spr, ring), t0) in enumerate(zip(self.spr, self.tt)):
            br, act = foc.get(t0, (1, 0))
            if prev is not None:
                xo = self.gone(t, "flow")
                k = M.line_progress(t, t0 - 0.5)
                if k > 0 and xo < 1:
                    a = (1 - xo) * vd
                    y0, y1 = prev, y
                    d.line((lx, y0, lx, y0 + (y1 - y0) * k), fill=C("accent", int(200 * a)), width=max(1, int(2.5 * z)))
                    if k >= 1:
                        d.ellipse((lx - 7 * z, y1 - 7 * z, lx + 7 * z, y1 + 7 * z), fill=C("bg"),
                                  outline=C("accent", int(255 * a)), width=int(3 * z))
                        for u, al in M.running_dot(t, t0 - 0.5 + M.fr(M.F_LINE)):
                            py = y0 + (y1 - y0) * u
                            d.ellipse((lx - 6 * z, py - 6 * z, lx + 6 * z, py + 6 * z), fill=C("accent", int(255 * al * a)))
            self.card(img, t, spr, self.area.x0, y, t0, act, br * vd, "bottom", name="flow", ph=i, T=T, ring=ring)
            prev = y + spr.height
            y += spr.height + self.gap

    def draw_body(self, img, t, T):
        if not self.wide:
            return self._draw_tall(img, t, T)
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


@template("diagram", aliases=("lab_diagram",),
          doc="lab · Center Diagram: одна схема по центру (узел с иконкой и подписью), ярлыки вокруг, линии от центра; "
              "эффект, механизм.",
          params={"center": P({"icon": "flask", "title": "Habit loop", "at": 0}, "узел по центру {icon, title, at}"),
                  "labels": P([{"text": "cue", "at": 1}], "ярлыки вокруг {text, at}"), **LabTemplate.COMMON},
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
        rx, ry = 520 * z, 300 * z
        if not self.wide:  # высокий кадр: эллипс ярлыков вытянут вниз, по ширине — до полей рамки
            mw = max((s.width for s, _ in self.lab_spr), default=0)
            cx, cy = self.area.cx, (self.top + self.area.y1) / 2 - 40 * z
            rx, ry = max(190 * z, (self.area.w - mw) / 2), 380 * z
        n = max(1, len(self.lb))
        d = ImageDraw.Draw(img, "RGBA")
        for i, ((spr, ring), t0) in enumerate(zip(self.lab_spr, self.lt)):
            ang = -math.pi / 2 + (i + 0.5) * math.tau / n if n > 2 else (math.pi if i == 0 else 0)
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


@template("chapter", aliases=("lab_chapter",),
          doc="lab · Карточка главы: «световой веер» 6 кадров → «01» в контуре + черта + заголовок капсом + подзаголовок "
              "моно + прогресс точками «chapter 1 of 8». Держать ≥ 2,5 с (min_duration). Между главами.",
          params={"number": P(1, "номер главы", int), "total": P(8, "всего глав", int), "title": P("Wake up", "заголовок"),
                  "subtitle": P("07:00 · facts 1–10", "подзаголовок моно"), **LabTemplate.COMMON},
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
                                   align="left" if self.wide else "center", maxw=int(900 * z if self.wide else self.area.w))
        self.subt = txt(p["subtitle"], 24 * z, "medium", "dim", "mono") if p.get("subtitle") else None
        self.prog = txt(ui(self.ctx.get("language"), "chapter_of").format(n=n, total=int(p.get('total', 8))), 20 * z, "medium", "dim", "mono", 0.04)
        self.n, self.total = n, int(p.get("total", 8))

    def draw_body(self, img, t, T):
        if not self.wide:
            return self._draw_tall(img, t, T)
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

    def _draw_tall(self, img, t, T):
        """Высокий кадр: столбик по центру — «01», горизонтальная черта, заголовок, подзаголовок; точки — внизу рамки."""
        z = self.z
        fk = M.prog(t, 0.0, M.fr(6) * 2)
        if fk < 1:  # световой веер сверху вниз
            fan = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(fan, "RGBA")
            cx, cy = self.W / 2, -100 * z
            a = math.sin(fk * math.pi)
            for i in range(9):
                ang = math.pi / 2 + (-0.5 + i / 8) * 1.1 + fk * 0.6
                d.polygon([(cx, cy), (cx + 2600 * z * math.cos(ang - 0.04), cy + 2600 * z * math.sin(ang - 0.04)),
                           (cx + 2600 * z * math.cos(ang + 0.04), cy + 2600 * z * math.sin(ang + 0.04))],
                          fill=C("accent", int(34 * a)))
            img.alpha_composite(fan.filter(ImageFilter.GaussianBlur(28 * z)))
        xo = self.gone(t, "chapter")
        cx = self.area.cx
        y = self.area.y0 + self.area.h * 0.42 - self.num.height
        k1 = M.ease_out_expo(M.prog(t, 0.15, M.fr(M.F_APPEAR)))
        put(img, self.num, cx - self.num.width / 2, y + (1 - k1) * 24 * z + M.bob(T, 1) * z, k1 * (1 - xo),
            0.96 + 0.04 * k1, (1 - k1) * 8)
        by = y + self.num.height + 30 * z
        lk = M.line_progress(t, 0.3, 18)
        d = ImageDraw.Draw(img, "RGBA")
        if lk > 0:
            w = 200 * z * lk
            d.line((cx - w / 2, by, cx + w / 2, by), fill=C("accent", int(255 * (1 - xo))), width=max(1, int(3 * z)))
        ty = by + 44 * z
        k2 = M.ease_out_expo(M.prog(t, 0.45, M.fr(M.F_APPEAR)))
        put(img, self.title, cx - self.title.width / 2, ty + (1 - k2) * 24 * z, k2 * (1 - xo))
        if self.subt is not None:
            k3 = M.ease_out_expo(M.prog(t, 0.6, M.fr(M.F_APPEAR)))
            put(img, self.subt, cx - self.subt.width / 2, ty + self.title.height + 20 * z + (1 - k3) * 24 * z, k3 * (1 - xo))
        k4 = M.ease_out_expo(M.prog(t, 0.8, M.fr(M.F_APPEAR))) * (1 - xo)
        if k4 > 0:
            y = self.area.y1 - 80 * z
            x0 = cx - (self.total * 26 * z) / 2
            for i in range(self.total):
                c = C("accent", int(255 * k4)) if i < self.n else (255, 255, 255, int(50 * k4))
                r = (6 if i == self.n - 1 else 4.5) * z
                d.ellipse((x0 + i * 26 * z - r, y - r, x0 + i * 26 * z + r, y + r), fill=c)
            put(img, self.prog, cx, y + 34 * z, k4, anchor="c")
