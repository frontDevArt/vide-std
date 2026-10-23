"""Свои элементы ролика «fake discounts» (briefs/fake-discounts.md, §4): якорь на цепи, шкала «perceived value» со
стрелкой, ярлыки вокруг бирки. Общее — ценник-бирка, чек, цепь, число с запятыми, иконки — в пакете
`studio.packs.commerce` и `lab` (P2.9).

Шаблон `lab_anchor` — Center Diagram; каждый блок необязателен (tag / anchor / gauge / labels / receipt), так что
один шаблон даёт и открывающую сцену (бирка + якорь), и сквозной «прибор» (шкала, якорь тянет стрелку).
Через склейку (SCENE_SPEC: только state): бирка — положение, масштаб, якорь, «просадка» и импульсы качания
в глобальном времени (`fd_tag`); строки чека и его видимость (`fd_receipt`).
Координаты — дизайн-пиксели 1920×1080, масштаб self.z.
"""
from __future__ import annotations

import functools
import math

from PIL import ImageDraw

from studio import gfx as G
from studio import motion as M
from studio.lab import C, LabTemplate, SS, _down, _ss_canvas, put, txt
from studio.packs.commerce import CommerceNumber, PriceTag, Receipt
from studio.packs.commerce.elements import chain, rot
from studio.templates import template

CHAIN = 64                              # цепь бирка → якорь
ANCHOR_INK = 214                        # низ «лап» якоря от верха спрайта (без отступа свечения)


# ===================================================================== sprites
@functools.lru_cache(maxsize=16)
def anchor_sprite(z):
    """Корабельный якорь линиями 2–3 тонов: кольцо, веретено, шток, рога с лапами. Цвет accent-2 («до», старая цена)."""
    w, h = int(200 * z), int(236 * z)
    img, d = _ss_canvas(w, h)
    k = SS * z
    c = C("accent2")
    lw = int(11 * k)
    cx = 100
    d.ellipse(((cx - 19) * k, 4 * k, (cx + 19) * k, 42 * k), outline=c, width=lw)
    d.line((cx * k, 42 * k, cx * k, 208 * k), fill=c, width=lw)
    d.line(((cx - 46) * k, 70 * k, (cx + 46) * k, 70 * k), fill=c, width=lw)
    for sx in (-46, 46):
        d.ellipse(((cx + sx - 8) * k, 62 * k, (cx + sx + 8) * k, 78 * k), fill=c)
    d.arc(((cx - 84) * k, 92 * k, (cx + 84) * k, 214 * k), 12, 168, fill=c, width=lw)
    for side in (-1, 1):
        a = math.radians(12 if side > 0 else 168)
        ex, ey = cx + 84 * math.cos(a), 153 + 61 * math.sin(a)
        d.polygon([((ex + side * 10) * k, (ey - 40) * k), ((ex - side * 16) * k, (ey + 6) * k), ((ex + side * 20) * k, (ey + 8) * k)], fill=c)
    d.ellipse(((cx - 9) * k, 200 * k, (cx + 9) * k, 216 * k), fill=c)
    base = _down(img, w, h)
    spr = G.glowify(base, "accent2", 9 * z, 0.35)
    pad = (spr.width - base.width) // 2
    return spr, pad


# ===================================================================== template
@template("lab_anchor",
          doc="lab · Center Diagram ролика fake-discounts: ценник-бирка на верёвочке (зачёркивание accent-2, новая цена "
              "пружиной), якорь на цепи, шкала «perceived value» со стрелкой, которую тянет якорь, ярлыки вокруг, чек "
              "Money Brain справа. Блоки необязательны; бирка и чек переходят через склейку (from_prev / keep).",
          params={"tag": {"was": "$199", "now": "$99", "x": 960, "y": 200, "scale": 1.0, "at": 0,
                          "strike_at": None, "now_at": None, "from_prev": False},
                  "anchor": {"at": None, "drop_at": None},
                  "gauge": {"at": None, "label": "PERCEIVED VALUE", "x0": 200, "x1": 1340, "y": 800,
                            "needle": {"from": 0.3, "to": 0.62, "at": None, "pull_at": None, "label": "FEELS WORTH"},
                            "land": 0.9},
                  "labels": [{"text": "deal?", "at": None}],
                  "receipt": {"lines": [{"text": "ANCHOR / $1|$0.77", "at": None}], "tear_at": None,
                              "tear_to": {"x": 960, "y": 560, "scale": 1.7, "rot": -4}},
                  **LabTemplate.COMMON},
          beats="всё по словам-триггерам `at`; tag.y — длина верёвки до люверса; receipt.tear_at — чек отрывается "
                "и выезжает в tear_to (строка без «|» — итог по центру)")
class LabAnchor(PriceTag, Receipt, LabTemplate):
    TAG_STATE = "fd_tag"
    RC_STATE = "fd_receipt"
    RC_TITLE = "MONEY BRAIN · RECEIPT"

    # ------------------------------------------------------------------ plan
    def plan_body(self):
        p = self.p
        prev = self.tag_plan()
        tg = self.tg
        an = p.get("anchor") or {}
        had_anchor = bool(prev.get("anchor"))
        self.t_attach = -10.0 if had_anchor else self.at(an.get("at"), None)
        if self.t_attach is not None and self.t_attach > 0:
            self.imps.append((self.T0 + self.t_attach + 0.22, -5.5))
        self.t_rel = self.at(an.get("drop_at"), None) if (self.t_attach is not None or not tg) else None
        if self.t_rel is not None:
            self.imps.append((self.T0 + self.t_rel + 0.05, 8.0))
        self.sink0 = float(prev.get("sink", 0.0))
        g = p.get("gauge")
        self.g = g
        if g:
            nd = g.get("needle") or {}
            self.t_g = self.at(g.get("at"), 0.3)
            self.t_n = self.at(nd.get("at"), self.t_g + 0.5)
            self.t_pull = self.at(nd.get("pull_at"), None)
        self.lbs = p.get("labels") or []
        self.t_lb = self.seq_times(self.lbs, 0.8)
        self.receipt_plan()

    def state_out(self):
        out = super().state_out()
        self.plan()
        out[self.TAG_STATE] = self.tag_state()
        out[self.RC_STATE] = self.receipt_state()
        return out

    def sfx_body(self):
        ev = self.tag_sfx()
        if self.t_attach is not None and self.t_attach > 0:
            ev.append((self.t_attach + 0.2, "pop"))
        if self.t_rel is not None:
            ev += [(self.t_rel, "swish"), (self.t_rel + 0.75, "pop")]
        if self.g:
            ev.append((self.t_g, "pop"))
            ev.append((self.t_n, "pop"))
            if self.t_pull is not None:
                ev += self.ticks(self.t_pull, 0.8)
        ev += [(x, "pop") for x in self.t_lb]
        return ev + self.receipt_sfx()

    # ------------------------------------------------------------------ setup
    def setup_body(self):
        z = self.z
        if self.tg:
            self.tag_setup()
        self.anc, self.anc_pad = anchor_sprite(z * self.anchor_scale())
        self.lb_spr = []
        for l in self.lbs:
            t = G.text_sprite(l.get("text", ""), int(30 * z), "bold", "text", family="head")
            w, h = int(t.width + 48 * z), int(t.height + 28 * z)
            img, d = _ss_canvas(w, h)
            d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 200), outline=C("accent2", 150), width=int(1.5 * z * SS))
            pill = _down(img, w, h)
            pill.alpha_composite(t, (int(24 * z), int((h - t.height) / 2)))
            self.lb_spr.append(pill)
        if self.g:
            self.g_lab = txt(str(self.g.get("label", "PERCEIVED VALUE")).upper() + "  →", 22 * z, "medium", "dim", "mono", 0.08)
            nd = self.g.get("needle") or {}
            t = txt(str(nd.get("label", "FEELS WORTH")).upper(), 20 * z, "medium", "accent", "mono", 0.08)
            w, h = int(t.width + 36 * z), int(44 * z)
            img, d = _ss_canvas(w, h)
            d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 220), outline=C("accent", 150), width=int(1.5 * z * SS))
            self.n_pill = _down(img, w, h)
            self.n_pill.alpha_composite(t, (int(18 * z), int((h - t.height) / 2)))

    def anchor_scale(self):
        tg = self.tg
        return float(tg.get("scale", 1.0)) if tg else float((self.p.get("anchor") or {}).get("scale", 0.75))

    def tag_focus(self, t):
        # шкала появилась — бирка уходит в фон
        if self.g:
            return M.lerp(1.0, M.DIM, M.ease_in_out(M.prog(t, self.t_g, M.fr(M.F_FOCUS))))
        return 1.0

    # ------------------------------------------------------------------ draw
    def draw_body(self, img, t, T):
        vd = self.vdim(t)
        d = ImageDraw.Draw(img, "RGBA")
        if self.g:
            self.draw_gauge(img, d, t, T, vd)
        hang = None
        if self.tg:
            hang = self.draw_tag(img, d, t, T, vd)
        self.draw_anchor(img, d, t, T, vd, hang)
        self.draw_labels(img, d, t, T, vd, hang)
        self.draw_receipt(img, t, T, vd)

    def anchor_center(self, ring, ang):
        """Центр спрайта якоря по точке кольца (верх) и углу."""
        z = self.z * self.anchor_scale()
        off = self.anc.height / 2 - (self.anc_pad + 6 * z)
        return ring[0] + rot(0, off, ang)[0], ring[1] + rot(0, off, ang)[1]

    def land_point(self):
        g = self.g
        z = self.z
        x = M.lerp(g.get("x0", 200), g.get("x1", 1340), float(g.get("land", 0.9))) * z
        za = z * self.anchor_scale()
        ring_y = g.get("y", 800) * z - (ANCHOR_INK - 6) * za
        return x, ring_y

    def draw_anchor(self, img, d, t, T, vd, hang):
        if self.t_attach is None and self.t_rel is None:
            return
        z = self.z
        s = self.anchor_scale()
        k_in = M.prog(t, self.t_attach, 0.35) if self.t_attach is not None else float(t >= self.t_rel)
        if k_in <= 0:
            return
        if self.t_rel is None or t < self.t_rel:
            if hang is None:
                return
            a = min(1.0, k_in * 2.5) * hang["a"]  # висит на бирке: гаснет и уходит вместе с ней
            bx, by = hang["b"]
            phi = self.swing(T - 0.14) * 1.2
            Lc = CHAIN * s * z * M.ease_out_expo(M.prog(t, self.t_attach, 0.25))
            ring = bx + rot(0, Lc, phi)[0], by + rot(0, Lc, phi)[1]
            chain(d, (bx, by), ring, 0, z, a)
            drop = (1 - M.spring(M.prog(t, self.t_attach + 0.05, 0.5))) * 46 * z
            cx, cy = self.anchor_center((ring[0], ring[1] - drop), phi)
            put(img, self.anc, cx, cy, a, M.lerp(0.85, 1.0, M.ease_out_expo(k_in)), rot=phi, anchor="c")
            return
        # полёт на шкалу: от точки, где висел в момент отцепления, дугой к месту посадки
        r0 = self._ring_at(self.t_rel)
        r1 = self.land_point()
        u = M.prog(t, self.t_rel, 0.75)
        e = M.ease_in(u) * 0.55 + M.ease_in_out(u) * 0.45
        x = M.lerp(r0[0], r1[0], M.ease_in_out(u))
        y = M.lerp(r0[1], r1[1], e) - 150 * z * math.sin(math.pi * u) * (1 - u * 0.4)
        v = t - (self.t_rel + 0.75)
        ang = M.lerp(self._phi_rel, -18, M.ease_in_out(min(1.0, u * 1.2))) if v < 0 else -18 * math.exp(-v * 5) * math.cos(v * 13)
        if v > 0:
            y -= 10 * z * math.exp(-v * 6) * abs(math.sin(v * 15))
        cx, cy = self.anchor_center((x, y), ang)
        put(img, self.anc, cx, cy, vd, rot=ang, anchor="c")
        self.anchor_ring_now = (x, y)
        # пыль удара
        if 0 < v < 0.5:
            r = (30 + 160 * v) * z
            gy = self.g.get("y", 800) * z
            al = int(120 * (1 - v / 0.5) * vd)
            d.ellipse((x - r, gy - r * 0.18, x + r, gy + r * 0.18), outline=C("accent2", al), width=max(1, int(2 * z)))

    def _ring_at(self, t):
        """Где было кольцо якоря в момент t (для старта полёта); без бирки — падает сверху из-за кадра."""
        if not self.tg:
            self._phi_rel = 0.0
            return self.land_point()[0] - 120 * self.z, -260 * self.z
        T = self.T0 + t
        bx, by = self.tag_bottom(t, T)
        phi = self.swing(T - 0.14) * 1.2
        self._phi_rel = phi
        Lc = CHAIN * self.tag_pose(t)[2] * self.z
        return bx + rot(0, Lc, phi)[0], by + rot(0, Lc, phi)[1]

    def draw_gauge(self, img, d, t, T, vd):
        z = self.z
        g = self.g
        x0, x1, y = g.get("x0", 200) * z, g.get("x1", 1340) * z, g.get("y", 800) * z
        xo = self.gone(t, "gauge")
        a = (1 - xo) * vd
        k = M.line_progress(t, self.t_g, 24)
        if k <= 0:
            return
        y += M.bob(T, 0.7) * z
        d.line((x0, y, x0 + (x1 - x0) * k, y), fill=(255, 255, 255, int(60 * a)), width=max(1, int(4 * z)))
        n = 24
        for i in range(n + 1):
            xi = x0 + (x1 - x0) * i / n
            if xi > x0 + (x1 - x0) * k:
                break
            hgt = (16 if i % 6 == 0 else 8) * z
            d.line((xi, y + 6 * z, xi, y + 6 * z + hgt), fill=(255, 255, 255, int((70 if i % 6 == 0 else 38) * a)), width=max(1, int(2 * z)))
        put(img, self.g_lab, x0, y + 38 * z, M.ease_out_expo(M.prog(t, self.t_g + 0.3, M.fr(M.F_APPEAR))) * a)
        # стрелка «сколько это стоит в голове»
        nd = g.get("needle") or {}
        kn = M.prog(t, self.t_n, 0.5)
        if kn <= 0:
            return
        u0, u1 = float(nd.get("from", 0.3)), float(nd.get("to", 0.62))
        pu = M.ease_in_out(M.prog(t, self.t_pull, 1.0)) if self.t_pull is not None else 0.0
        u = M.lerp(u0, u1, pu)
        xn = x0 + (x1 - x0) * u
        an = min(1.0, kn * 2.5) * a
        drop = (1 - M.spring(kn)) * 40 * z
        # заливка до стрелки
        d.rounded_rectangle((x0, y - 3 * z, xn, y + 3 * z), 3 * z, fill=C("accent", int(150 * an)))
        top = y - 100 * z - drop
        d.line((xn, y - 24 * z - drop, xn, top), fill=C("accent", int(255 * an)), width=max(1, int(4 * z)))
        d.polygon([(xn - 13 * z, y - 28 * z - drop), (xn + 13 * z, y - 28 * z - drop), (xn, y - 6 * z - drop)], fill=C("accent", int(255 * an)))
        put(img, G.radial(int(46 * z), "accent", 0.9, 2.0), xn, y, an * 0.8, anchor="c")
        put(img, self.n_pill, xn, top - 30 * z, an, anchor="c")
        self.needle_top = (xn, top + 10 * z)
        # цепь стрелка ↔ якорь (после посадки)
        if self.t_rel is not None and t > self.t_rel + 0.75:
            kc = M.ease_out_expo(M.prog(t, self.t_rel + 0.8, 0.35))
            r1 = self.land_point()
            ring = (r1[0], r1[1] + 4 * z)
            p1 = (xn + (ring[0] - xn) * kc, top + 10 * z + (ring[1] - top - 10 * z) * kc)
            sag = 48 * z * (1 - pu) if self.t_pull is not None else 48 * z
            chain(d, (xn, top + 10 * z), p1, sag * kc, z, an, "accent2")

    def draw_labels(self, img, d, t, T, vd, hang):
        z = self.z
        if not self.lb_spr:
            return
        cx = hang["c"][0] if hang else self.W / 2
        cy = hang["c"][1] if hang else self.H * 0.45
        for i, (spr, t0) in enumerate(zip(self.lb_spr, self.t_lb)):
            side = -1 if i % 2 == 0 else 1
            lx = cx + side * (330 * z) - (spr.width if side < 0 else 0)
            ly = (360 + 150 * (i // 2) + 70 * (i % 2)) * z
            k = M.line_progress(t, t0 - 0.2, 14)
            xo = self.gone(t, "labels")
            if k > 0:
                ex = cx + side * 140 * z
                sx = lx + (spr.width if side < 0 else 0)
                yy = ly + spr.height / 2
                d.line((sx, yy, sx + (ex - sx) * k, yy + (cy - 40 * z - yy) * k), fill=C("accent2", int(130 * vd * (1 - xo))), width=max(1, int(2 * z)))
            self.card(img, t, spr, lx, ly, t0, 0.0, vd, "bottom", name="labels", ph=i, T=T)


# ===================================================================== Full Number с разделителями тысяч
@template("fd_number",
          doc="lab_full_number ролика fake-discounts: то же, но числа ≥ 1000 с запятыми ($14,550) и опц. `decimals` "
              "(0,77 → 77¢ задавайте как value 77 + suffix ¢). Общая версия — commerce.number.",
          params=dict(CommerceNumber.PARAMS),
          beats=CommerceNumber.BEATS)
class FdNumber(CommerceNumber):
    pass
