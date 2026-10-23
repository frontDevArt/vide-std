"""Свои элементы ролика «coffee-wake» (STYLE §14, новый элемент): кружка-шкала бодрости.

Шаблон `lab_mug` — Center Diagram: плоская кружка-«стекло», уровень жидкости = бодрость (ALERTNESS). Пунктир
`baseline` — норма человека без кофеина. Выше пунктира жидкость бренд-циан (accent), ниже — accent-2 («до»,
ломка); на уровне нормы и выше над кружкой идёт пар. Уровень едет по словам-триггерам (`moves`), ярлыки — справа
столбиком (в высоком кадре — под кружкой).
Через склейку (SCENE_SPEC: только state): уровень, положение и видимость пунктира (`cw_mug`), если в `keep` есть `mug`
и у следующей сцены `mug.from_prev: true`.
Координаты — дизайн-пиксели 1920×1080, масштаб self.z; высокий кадр — своя раскладка в рамке self.area.
"""
from __future__ import annotations

import functools
import math

from PIL import ImageDraw

from studio import gfx as G
from studio import motion as M
from studio.lab import C, LabTemplate, SS, _down, _focus_list, _ss_canvas, glass, put, ring_pad, txt
from studio.templates import template

BW, BH, BR = 360, 430, 76        # корпус кружки (дизайн-px): ширина, высота, радиус низа
INSET = 16                       # стенка: жидкость внутри корпуса
MOVE = 0.9                       # переезд уровня, с
STATE = "cw_mug"


# ===================================================================== sprites
@functools.lru_cache(maxsize=8)
def mug_sprite(z):
    """Корпус-стекло + ручка + деления слева. Линии text-dim, заливка bg2 (как карточки §5)."""
    pad = int(40 * z)
    w, h = int((BW + 130) * z) + 2 * pad, int(BH * z) + 2 * pad
    img, d = _ss_canvas(w, h)
    k = SS * z
    x0, y0 = pad * SS, pad * SS
    x1, y1 = x0 + BW * k, y0 + BH * k
    d.rounded_rectangle((x0, y0 - BR * k, x1, y1), BR * k, fill=C("bg2", 170))
    d.rectangle((x0 - 2 * k, y0 - BR * k - 2 * k, x1 + 2 * k, y0), fill=(0, 0, 0, 0))  # срезать скругление сверху
    lw = int(6 * k)
    d.line((x0, y0, x0, y1 - BR * k), fill=C("dim"), width=lw)
    d.line((x1, y0, x1, y1 - BR * k), fill=C("dim"), width=lw)
    d.arc((x0, y1 - 2 * BR * k, x0 + 2 * BR * k, y1), 90, 180, fill=C("dim"), width=lw)
    d.arc((x1 - 2 * BR * k, y1 - 2 * BR * k, x1, y1), 0, 90, fill=C("dim"), width=lw)
    d.line((x0 + BR * k, y1 - lw / 2, x1 - BR * k, y1 - lw / 2), fill=C("dim"), width=lw)
    d.line((x0 - 10 * k, y0, x0 + 26 * k, y0), fill=C("text", 150), width=lw)       # кромка
    d.line((x1 - 26 * k, y0, x1 + 10 * k, y0), fill=C("text", 150), width=lw)
    # ручка
    d.arc((x1 - 70 * k, y0 + 70 * k, x1 + 110 * k, y0 + 270 * k), 270, 90, fill=C("dim"), width=int(22 * k))
    d.arc((x1 - 70 * k, y0 + 70 * k, x1 + 110 * k, y0 + 270 * k), 270, 90, fill=C("bg2"), width=int(10 * k))
    base = _down(img, w, h)
    return base, pad


@functools.lru_cache(maxsize=8)
def liquid_sprite(z, color):
    """Внутренность корпуса, залитая цветом; кадр берёт нижнюю часть по уровню."""
    w, h = int((BW - 2 * INSET) * z), int((BH - INSET) * z)
    r = (BR - INSET) * z
    img, d = _ss_canvas(w, h)
    d.rounded_rectangle((0, -r * SS, w * SS, h * SS), r * SS, fill=C(color, 215))
    return _down(img, w, h)


@functools.lru_cache(maxsize=4)
def ticks_sprite(z):
    """Шкала слева от кружки: 5 делений + подпись ALERTNESS сверху."""
    w, h = int(60 * z), int((BH - INSET) * z)
    img, d = _ss_canvas(w, h)
    for i in range(6):
        y = (h - 2) * SS * i / 5 + SS
        ln = (34 if i % 5 == 0 else 20) * z * SS
        d.line((w * SS - ln, y, w * SS, y), fill=(255, 255, 255, 70), width=int(2 * z * SS))
    return _down(img, w, h)


# ===================================================================== template
@template("lab_mug",
          doc="lab · Center Diagram ролика coffee-wake: кружка-шкала бодрости. Уровень жидкости = alertness, "
              "пунктир baseline = норма без кофеина; ниже нормы — accent-2 (ломка), выше — циан и пар. "
              "Уровень едет по `moves`, ярлыки справа. Кружка переходит через склейку (keep: [mug] + mug.from_prev).",
          params={"mug": {"level": 0.6, "at": 0, "from_prev": False, "x": 620},
                  "moves": [{"to": 0.85, "at": None}],
                  "baseline": {"level": 0.6, "label": "BASELINE · NO CAFFEINE", "at": None},
                  "labels": [{"text": "boost?", "at": None, "color": "accent"}],
                  **LabTemplate.COMMON},
          beats="всё по словам-триггерам `at`; moves[i].to — уровень 0..1, переезд 0,9 с")
class LabMug(LabTemplate):
    # ------------------------------------------------------------------ plan
    def plan_body(self):
        p = self.p
        prev = self.state.get(STATE) or {}
        mg = p.get("mug") or {}
        self.carry = bool(mg.get("from_prev")) and bool(prev)
        self.lv0 = float(prev.get("level", mg.get("level", 0.6))) if self.carry else float(mg.get("level", 0.6))
        self.x_to = float(mg.get("x", 620))
        self.x_from = float(prev.get("x", self.x_to)) if self.carry else self.x_to
        self.t_mug = -10.0 if self.carry else self.at(mg.get("at"), 0.2)
        self.moves = []
        lv = self.lv0
        for i, mv in enumerate(p.get("moves") or []):
            t0 = self.at(mv.get("at"), 0.8 + 1.2 * i)
            self.moves.append((t0, lv, float(mv.get("to", lv))))
            lv = float(mv.get("to", lv))
        self.lv_end = lv
        bl = p.get("baseline")
        self.bl = bl
        if bl:
            self.b_lv = float(bl.get("level", 0.6))
            self.t_b = -10.0 if (self.carry and prev.get("baseline")) else self.at(bl.get("at"), 0.6)
        self.lbs = p.get("labels") or []
        self.t_lb = self.seq_times(self.lbs, 1.0)
        self.fl = _focus_list(self.t_lb, self.v_t or self.exit_t)

    def state_out(self):
        out = super().state_out()
        out[STATE] = ({"level": self.lv_end, "x": self.x_to, "baseline": bool(self.bl)}
                      if "mug" in self.keep else None)
        return out

    def sfx_body(self):
        ev = [] if self.carry else [(self.t_mug, "pop")]
        if self.bl and self.t_b > 0:
            ev.append((self.t_b, "pop"))
        for t0, a, b in self.moves:
            ev.append((t0, "swish"))
            ev += self.ticks(t0 + 0.1, MOVE * 0.8)
        return ev + [(x, "pop") for x in self.t_lb]

    # ------------------------------------------------------------------ setup
    def setup_body(self):
        z = self.z
        self.mug, self.pad = mug_sprite(z)
        self.liq = {c: liquid_sprite(z, c) for c in ("accent", "accent2")}
        self.ticks_spr = ticks_sprite(z)
        self.axis = txt("ALERTNESS ↑", 20 * z, "medium", "dim", "mono", 0.08)
        if self.bl:
            t = txt(str(self.bl.get("label", "BASELINE")).upper(), 20 * z, "medium", "text", "mono", 0.08)
            w, h = int(t.width + 36 * z), int(44 * z)
            img, d = _ss_canvas(w, h)
            d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 220),
                                outline=(255, 255, 255, 60), width=int(1.5 * z * SS))
            self.b_pill = _down(img, w, h)
            self.b_pill.alpha_composite(t, (int(18 * z), int((h - t.height) / 2)))
        self.lb_spr = []
        for lb in self.lbs:
            col = lb.get("color", "accent")
            t = G.text_sprite(str(lb.get("text", "")), int(32 * z), "bold", "text", family="head", maxw=int(520 * z))
            w, h = int(t.width + 56 * z), int(t.height + 32 * z)
            card = glass(w, h, int(14 * z)).copy()
            d = ImageDraw.Draw(card, "RGBA")
            d.rounded_rectangle((int(14 * z), int(h / 2 - 6 * z), int(26 * z), int(h / 2 + 6 * z)), int(6 * z), fill=C(col))
            card.alpha_composite(t, (int(40 * z), int(16 * z)))
            self.lb_spr.append((card, ring_pad(w, h, int(14 * z), col)))

    # ------------------------------------------------------------------ geometry
    def level(self, t):
        lv = self.lv0
        for t0, a, b in self.moves:
            if t >= t0:
                lv = M.lerp(a, b, M.ease_in_out(M.prog(t, t0, MOVE)))
        return lv

    def body_xy(self, t):
        """Левый верхний угол корпуса кружки (дизайн-рамка → пиксели)."""
        z = self.z
        if self.wide:
            k = M.ease_in_out(M.prog(t, 0.0, M.fr(M.F_MORPH))) if self.carry else 1.0
            cx = M.lerp(self.x_from, self.x_to, k) * z
            return cx - BW * z / 2, 300 * z
        a = self.area
        return a.cx - BW * z / 2 - 40 * z, self.top + 90 * z

    # ------------------------------------------------------------------ draw
    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        d = ImageDraw.Draw(img, "RGBA")
        k_in = M.ease_out_expo(M.prog(t, self.t_mug, M.fr(M.F_APPEAR)))
        xo = self.gone(t, "mug")
        a = k_in * (1 - xo) * vd
        bx, by = self.body_xy(t)
        by += M.bob(T, 0.4) * z + (1 - k_in) * 24 * z + xo * 12 * z
        ih = (BH - INSET) * z                       # высота внутренности
        ix, iy = bx + INSET * z, by                 # верх внутренности = кромка
        if a > 0:
            put(img, self.ticks_spr, bx - 80 * z, iy, a * 0.9)
            put(img, self.axis, bx - 80 * z, iy - 46 * z, a)
            # жидкость: нижняя часть спрайта по уровню; цвет по отношению к норме
            lv = self.level(t)
            b = self.b_lv if self.bl else 0.0
            cool = M.ease_in_out(min(1.0, max(0.0, (lv - b + 0.06) / 0.05))) if self.bl else 1.0
            top = ih * (1 - lv)
            if lv > 0.005:
                for c, al in (("accent", cool), ("accent2", 1 - cool)):
                    if al > 0.01:
                        spr = self.liq[c]
                        crop = spr.crop((0, int(top), spr.width, spr.height))
                        put(img, crop, ix, iy + int(top), a * al)
                # поверхность: светлая линия с лёгкой волной
                sy = iy + top + math.sin(T * 2.4) * 2 * z
                c = "accent" if cool > 0.5 else "accent2"
                d.line((ix + 4 * z, sy, ix + (BW - 2 * INSET) * z - 4 * z, sy), fill=C(c, int(255 * a)), width=max(1, int(4 * z)))
                put(img, G.radial(int(90 * z), c, 0.7, 2.0), ix + (BW - 2 * INSET) * z / 2, sy, a * 0.5, anchor="c")
            put(img, self.mug, bx - self.pad, by - self.pad, a)
            # пар: на уровне нормы и выше
            steam = cool * a
            if steam > 0.02:
                for j in range(3):
                    sx = bx + (BW / 2 - 70 + 70 * j) * z
                    ph = T * 1.6 + j * 1.3
                    pts = [(sx + math.sin(ph + u * 5) * 12 * z, by - 30 * z - u * 120 * z) for u in (i / 10 for i in range(11))]
                    al = int(110 * steam * (0.6 + 0.4 * math.sin(ph)))
                    d.line(pts, fill=(255, 255, 255, max(0, al)), width=max(1, int(4 * z)), joint="curve")
        # пунктир нормы
        if self.bl:
            kb = M.line_progress(t, self.t_b, 20)
            ab = (1 - xo) * vd
            if kb > 0 and ab > 0:
                yb = iy + ih * (1 - self.b_lv)
                x0 = bx - 40 * z
                x1 = bx + (BW + 110) * z if self.wide else min(self.area.x1, bx + (BW + 110) * z)
                xe = x0 + (x1 - x0) * kb
                x = x0
                while x < xe:
                    d.line((x, yb, min(x + 18 * z, xe), yb), fill=C("text", int(200 * ab)), width=max(1, int(3 * z)))
                    x += 30 * z
                if self.wide:
                    put(img, self.b_pill, x1 + 16 * z, yb - self.b_pill.height / 2, ab * kb)
                else:
                    put(img, self.b_pill, self.area.x1 - self.b_pill.width, yb + 20 * z, ab * kb)
        # ярлыки
        foc = {s: M.focus(t, s, e) for s, e in self.fl}
        for i, ((spr, ring), t0) in enumerate(zip(self.lb_spr, self.t_lb)):
            if self.wide:
                lx, ly = 1340 * z, (250 + 130 * i) * z
            else:
                lx, ly = self.area.x0 + 20 * z, by + (BH + 70) * z + 100 * z * i
            br, act = foc.get(t0, (1, 0))
            self.card(img, t, spr, lx, ly, t0, act, br * vd, "right", name="labels", ph=i, T=T, ring=ring)
