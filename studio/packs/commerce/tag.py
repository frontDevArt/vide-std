"""Пакет commerce: ценник-бирка на верёвочке — миксин для шаблонов lab (`PriceTag`).

Бирка висит на гвоздике у верха безопасной зоны (верёвка не уходит за кадр — ROADMAP B3): падает от гвоздика на всю
длину верёвки, качается (импульсы в глобальном времени), старая цена зачёркивается, новая выпрыгивает пружиной.
Координаты бирки (`x`, `y`) — в сетке 1920×1080; в высоком кадре (9:16, 4:5, 1:1) бирка висит у центра рамки шаблона
(`self.area`), смещение `x` ужато (`TALL_DX`), верёвка длиннее на шапку (`TALL_ROPE`).
К бирке можно подвесить груз (`t_attach` → «просадка» верёвки, `t_rel` — груз отцеплен): так в fake-discounts висит
якорь. Через склейку — только state (`TAG_STATE`): положение, масштаб, груз, просадка, импульсы качания.
"""
from __future__ import annotations

import math

from PIL import ImageDraw

from ... import gfx as G
from ... import motion as M
from ..lab.elements import C, put
from .elements import HOLE_Y, TAG_H, rot, tag_parts

TALL_DX = 0.35    # высокий кадр: доля смещения x бирки от центра (сетка 1920 шире рамки вдвое с лишним)
TALL_ROPE = 160   # высокий кадр: верёвка длиннее на столько дизайн-px — бирка ниже шапки, ближе к центру
NAIL = 7          # радиус гвоздика, дизайн-px

TAG_DEFAULTS = {"was": "$199", "now": "$99", "x": 960, "y": 200, "scale": 1.0, "at": 0,
                "strike_at": None, "now_at": None, "from_prev": False}


class PriceTag:
    """Миксин к LabTemplate: параметр `tag` ({was, now, x, y, scale, at, strike_at, now_at, from_prev, was_label,
    now_label}); tag.y — длина верёвки до люверса. Шаблон зовёт tag_plan / tag_sfx / tag_setup / draw_tag, а в
    state_out — tag_state."""
    TAG_STATE = "price_tag"
    t_attach = None   # груз подвешен (сек сцены) — переопределяет шаблон
    t_rel = None      # груз отцеплен
    sink0 = 0.0       # просадка, унаследованная от прошлой сцены

    # ------------------------------------------------------------------ plan
    def tag_plan(self):
        """Времена бирки и импульсы качания. -> state прошлой сцены (from_prev) или {}."""
        p = self.p
        self.T0 = self.s.get("start_frame", 0) / self.fps
        tg = p.get("tag")
        self.tg = tg
        prev = (self.state.get(self.TAG_STATE) or {}) if tg and tg.get("from_prev") else {}
        self.tprev = prev or None
        self.imps = [tuple(x) for x in (prev.get("imps") or []) if self.T0 - x[0] < 5]
        if tg:
            if prev:
                self.t_drop = -10.0
                self.t_strike = -10.0
                self.t_now = -10.0
            else:
                self.t_drop = self.at(tg.get("at", 0), 0.0)
                self.t_strike = self.at(tg.get("strike_at"), None)
                self.t_now = self.at(tg.get("now_at"), None)
                self.imps.append((self.T0 + self.t_drop + 0.55, 7.0))
            if self.t_strike is not None and self.t_strike > 0:
                self.imps.append((self.T0 + self.t_strike + 0.15, 2.4))
            if self.t_now is not None and self.t_now > 0:
                self.imps.append((self.T0 + self.t_now + 0.1, -3.2))
        return prev

    def tag_state(self):
        """Значение state[TAG_STATE] для следующей сцены (None — бирка не переходит)."""
        tg = self.tg
        if not (tg and "tag" in self.keep):
            return None
        anchored = self.t_attach is not None and self.t_rel is None
        s = float(tg.get("scale", 1.0))
        return {"was": tg.get("was", "$199"), "now": tg.get("now", "$99"), "x": tg.get("x", 960), "y": tg.get("y", 200),
                "scale": s, "anchor": anchored, "sink": 18.0 * s if anchored else 0.0,
                "imps": [list(x) for x in self.imps]}

    def tag_sfx(self):
        ev = []
        if self.tg and not self.tprev:
            ev.append((self.t_drop + 0.5, "pop"))
            if self.t_strike is not None:
                ev.append((self.t_strike, "swish"))
            if self.t_now is not None:
                ev.append((self.t_now, "pop"))
        return ev

    # ------------------------------------------------------------------ setup
    def tag_setup(self):
        tg = self.tg
        s1 = float(tg.get("scale", 1.0))
        s0 = float(self.tprev.get("scale", s1)) if self.tprev else s1
        self.s_spr = max(s0, s1)
        labels = {k: tg[k] for k in ("was_label", "now_label") if tg.get(k)}
        self.tag_spr = tag_parts(tg.get("was", "$199"), tg.get("now", "$99"), self.z * self.s_spr, **labels)
        self._tag_done = None

    # ------------------------------------------------------------------ geometry
    def tag_xy(self, x, y):
        """Дизайн-координаты бирки (x гвоздика, y — глубина люверса, сетка 1920×1080) → пиксели кадра."""
        z = self.z
        if self.wide:
            return x * z, y * z
        return self.area.cx + (x - 960) * z * TALL_DX, self.area.y0 + (y + TALL_ROPE) * z

    def pivot_y(self):
        """Высота гвоздика: верх безопасной зоны (16:9) или рамки шаблона (высокий кадр)."""
        return self.safe.y0 if self.wide else self.area.y0

    def swing(self, T):
        a = 1.3 * math.sin(T * math.tau / 5.2)
        for T0, A in self.imps:
            u = T - T0
            if u > 0:
                a += A * math.exp(-u / 0.95) * math.sin(u * math.tau / 1.5)
        return a

    def tag_pose(self, t):
        """-> (x гвоздика, глубина люверса в покое, масштаб) в пикселях кадра — с морфингом от прошлой сцены,
        «просадкой» под грузом и падением от гвоздика в начале."""
        z = self.z
        tg = self.tg
        x1, y1, s1 = float(tg.get("x", 960)), float(tg.get("y", 200)), float(tg.get("scale", 1.0))
        if self.tprev:
            m = M.ease_in_out(M.prog(t, 0.0, M.fr(M.F_MORPH)))
            pv = self.tprev
            x = M.lerp(float(pv["x"]), x1, m)
            y = M.lerp(float(pv["y"]), y1, m)
            s = M.lerp(float(pv["scale"]), s1, m)
            sink = self.sink0 * M.lerp(1, s1 / max(0.01, float(pv["scale"])), m)
        else:
            x, y, s = x1, y1, s1
            sink = 0.0
            if self.t_attach is not None:
                sink = 18 * s * M.spring(M.prog(t, self.t_attach + 0.18, 0.6))
        if self.t_rel is not None:
            sink *= 1 - M.spring(M.prog(t, self.t_rel, 0.6))
        px, gy = self.tag_xy(x, y + sink)
        # падение от гвоздика: верх бирки у гвоздика → вся длина верёвки
        if not self.tprev:
            k = M.spring(M.prog(t, self.t_drop, 0.75))
            gy = M.lerp(self.pivot_y() + HOLE_Y * s * z, gy, k) if k < 1 else gy
        return px, gy, s

    def tag_bottom(self, t, T):
        """Точка низа бирки (куда цепляется груз) в момент t сцены, T — глобальное время."""
        px, gy, s = self.tag_pose(t)
        th = self.swing(T)
        z = self.z
        py = self.pivot_y()
        hx, hy = px + rot(0, gy - py, th)[0], py + rot(0, gy - py, th)[1]
        return hx + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[0], hy + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[1]

    # ------------------------------------------------------------------ draw
    def tag_image(self, t):
        body, (sx0, sx1, sy), nlab, npr = self.tag_spr
        done = (self.t_strike is None or t > self.t_strike + 0.6) and (self.t_now is None or t > self.t_now + 0.8)
        if done and self._tag_done is not None:
            return self._tag_done
        img = body.copy()
        z = self.z * self.s_spr
        if self.t_strike is not None:
            k = M.ease_in_out(M.prog(t, self.t_strike, 0.4))
            if k > 0:
                d = ImageDraw.Draw(img, "RGBA")
                n = 24
                pts = []
                for i in range(int(n * k) + 1):
                    u = i / n
                    pts.append((sx0 + (sx1 - sx0) * u, sy + 9 * z - 18 * z * u + math.sin(u * 9.0) * 2.6 * z))
                if len(pts) > 1:
                    d.line(pts, fill=C("accent2", 80), width=int(20 * z), joint="curve")
                    d.line(pts, fill=C("accent2"), width=int(9 * z), joint="curve")
        if self.t_now is not None:
            k = M.prog(t, self.t_now, 0.6)
            if k > 0:
                sp = M.spring(k)
                cx = img.width / 2
                G.blitc(img, nlab, cx, 262 * z, min(1.0, k * 3))
                G.blitc(img, npr, cx, 338 * z, min(1.0, k * 3), M.lerp(0.4, 1.0, sp))
        if done:
            self._tag_done = img
        return img

    def tag_focus(self, t):
        """Множитель яркости бирки (шаблон приглушает её, когда фокус уходит на другой блок)."""
        return 1.0

    def draw_tag(self, img, d, t, T, vd):
        """Бирка на верёвке. -> {b: низ бирки, th: угол, s: масштаб, c: центр, a: альфа} или None (не видна)."""
        z = self.z
        px, gy, s = self.tag_pose(t)
        th = self.swing(T)
        xo = self.gone(t, "tag")
        foc = self.tag_focus(t)
        a = (1 - xo) * vd * foc
        if not self.tprev:
            a *= M.prog(t, self.t_drop, 0.12)  # бирка проявляется у гвоздика
        if a <= 0.004:
            return None
        py = self.pivot_y()
        hx, hy = (px + rot(0, gy - py, th)[0], py + rot(0, gy - py, th)[1])
        d.line((px, py, hx, hy), fill=C("dim", int(200 * a)), width=max(1, int(2.5 * z)))
        r = NAIL * z
        d.ellipse((px - r, py - r, px + r, py + r), fill=C("dim", int(230 * a)))
        sc = s / self.s_spr
        timg = self.tag_image(t)
        off = (TAG_H / 2 - HOLE_Y) * s * z
        cx, cy = hx + rot(0, off, th)[0], hy + rot(0, off, th)[1]
        put(img, timg, cx, cy, a, sc, rot=th, anchor="c")
        bx, by = hx + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[0], hy + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[1]
        return {"b": (bx, by), "th": th, "s": s, "c": (cx, cy), "a": a}

