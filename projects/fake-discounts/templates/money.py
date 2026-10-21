"""Свои элементы ролика «fake discounts» (briefs/fake-discounts.md, §4): ценник-бирка на верёвочке, якорь на цепи,
шкала «perceived value» со стрелкой, чек Money Brain сбоку кадра.

Шаблон `lab_anchor` — Center Diagram; каждый блок необязателен (tag / anchor / gauge / labels / receipt), так что
один шаблон даёт и открывающую сцену (бирка + якорь), и сквозной «прибор» (шкала, якорь тянет стрелку).
Через склейку (SCENE_SPEC: только state): бирка — положение, масштаб, якорь, «просадка» и импульсы качания
в глобальном времени (`fd_tag`); строки чека и его видимость (`fd_receipt`).
Координаты — дизайн-пиксели 1920×1080, масштаб self.z.
"""
from __future__ import annotations

import functools
import math

from PIL import Image, ImageDraw

from studio import gfx as G
from studio import motion as M
from studio.lab import C, LabTemplate, SS, _down, _ss_canvas, put, txt
from studio.templates import template

TAG_W, TAG_H, HOLE_Y = 360, 440, 46     # бирка в дизайн-пикселях при scale 1
CHAIN = 64                              # цепь бирка → якорь
ANCHOR_INK = 214                        # низ «лап» якоря от верха спрайта (без отступа свечения)


# ===================================================================== sprites
@functools.lru_cache(maxsize=16)
def tag_parts(was, now, z):
    """Корпус бирки (стекло, скошенный верх, люверс) + «WAS $199»; отдельно «NOW» и «$99» — они выпрыгивают."""
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
    lab = txt("WAS", 22 * z, "medium", "dim", "mono", 0.14)
    body.alpha_composite(lab, (int(w / 2 - lab.width / 2), int(96 * z)))
    pr = G.text_sprite(was, int(88 * z), "extrabold", "text", family="num")
    py = int(128 * z)
    body.alpha_composite(pr, (int(w / 2 - pr.width / 2), py))
    f = G.font(int(88 * z), "extrabold", "num")
    l, t, r, b = f.getbbox(was)
    iw = r - l
    strike = (w / 2 - iw / 2 - 14 * z, w / 2 + iw / 2 + 14 * z, py + (t + b) * 0.52)
    nlab = txt("NOW", 22 * z, "medium", "dim", "mono", 0.14)
    npr = G.glowify(G.text_sprite(now, int(116 * z), "extrabold", "accent", family="num"), "accent", 22 * z, 0.45)
    return body, strike, nlab, npr


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


def rot(vx, vy, deg):
    """Поворот вектора экранных координат на deg против часовой (как Image.rotate)."""
    a = math.radians(deg)
    return vx * math.cos(a) + vy * math.sin(a), -vx * math.sin(a) + vy * math.cos(a)


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
class LabAnchor(LabTemplate):
    # ------------------------------------------------------------------ plan
    def plan_body(self):
        p = self.p
        self.T0 = self.s.get("start_frame", 0) / self.fps
        tg = p.get("tag")
        self.tg = tg
        prev = (self.state.get("fd_tag") or {}) if tg and tg.get("from_prev") else {}
        self.tprev = prev or None
        self.imps = [tuple(x) for x in (prev.get("imps") or []) if self.T0 - x[0] < 5]
        an = p.get("anchor") or {}
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
        tg = self.tg
        if tg and "tag" in self.keep:
            anchored = self.t_attach is not None and self.t_rel is None
            s = float(tg.get("scale", 1.0))
            out["fd_tag"] = {"was": tg.get("was", "$199"), "now": tg.get("now", "$99"), "x": tg.get("x", 960), "y": tg.get("y", 200),
                             "scale": s, "anchor": anchored, "sink": 18.0 * s if anchored else 0.0,
                             "imps": [list(x) for x in self.imps]}
        else:
            out["fd_tag"] = None
        out["fd_receipt"] = {"lines": self.rc_all, "visible": bool(self.rc) and "receipt" in self.keep}
        return out

    def sfx_body(self):
        ev = []
        if self.tg and not self.tprev:
            ev.append((self.t_drop + 0.5, "pop"))
            if self.t_strike is not None:
                ev.append((self.t_strike, "swish"))
            if self.t_now is not None:
                ev.append((self.t_now, "pop"))
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
        ev += [(x, "tick") for x in self.rc_t]
        if self.t_tear is not None:
            ev += [(self.t_tear, "swish"), (self.t_tear + 0.8, "pop")]
        return ev

    # ------------------------------------------------------------------ setup
    def setup_body(self):
        z = self.z
        tg = self.tg
        if tg:
            s1 = float(tg.get("scale", 1.0))
            s0 = float(self.tprev.get("scale", s1)) if self.tprev else s1
            self.s_spr = max(s0, s1)
            self.tag_spr = tag_parts(tg.get("was", "$199"), tg.get("now", "$99"), z * self.s_spr)
            self._tag_done = None
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
        self.receipt_setup()

    def anchor_scale(self):
        tg = self.tg
        return float(tg.get("scale", 1.0)) if tg else float((self.p.get("anchor") or {}).get("scale", 0.75))

    # ------------------------------------------------------------------ tag geometry
    def swing(self, T):
        a = 1.3 * math.sin(T * math.tau / 5.2)
        for T0, A in self.imps:
            u = T - T0
            if u > 0:
                a += A * math.exp(-u / 0.95) * math.sin(u * math.tau / 1.5)
        return a

    def tag_pose(self, t):
        """-> (pivot x, длина верёвки, масштаб) с морфингом от прошлой сцены и «просадкой» под якорем."""
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
        # падение сверху в начале
        if not self.tprev:
            k = M.spring(M.prog(t, self.t_drop, 0.75))
            y = M.lerp(-TAG_H * s - 60, y, k) if k < 1 else y
        return x * z, (y + sink) * z, s

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

    # ------------------------------------------------------------------ draw
    def draw_body(self, img, t, T):
        z = self.z
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

    def draw_tag(self, img, d, t, T, vd):
        z = self.z
        px, ls, s = self.tag_pose(t)
        th = self.swing(T)
        xo = self.gone(t, "tag")
        foc = 1.0
        if self.g:
            foc = M.lerp(1.0, M.DIM, M.ease_in_out(M.prog(t, self.t_g, M.fr(M.F_FOCUS))))
        a = (1 - xo) * vd * foc
        if a <= 0.004:
            return None
        py = -40 * z
        hx, hy = (px + rot(0, ls + 40 * z, th)[0], py + rot(0, ls + 40 * z, th)[1])
        d.line((px, py, hx, hy), fill=C("dim", int(200 * a)), width=max(1, int(2.5 * z)))
        sc = s / self.s_spr
        timg = self.tag_image(t)
        off = (TAG_H / 2 - HOLE_Y) * s * z
        cx, cy = hx + rot(0, off, th)[0], hy + rot(0, off, th)[1]
        put(img, timg, cx, cy, a, sc, rot=th, anchor="c")
        bx, by = hx + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[0], hy + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[1]
        return {"b": (bx, by), "th": th, "s": s, "c": (cx, cy), "a": a}

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
        px, ls, s = self.tag_pose(t)
        th = self.swing(T)
        z = self.z
        py = -40 * z
        hx, hy = px + rot(0, ls + 40 * z, th)[0], py + rot(0, ls + 40 * z, th)[1]
        bx, by = hx + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[0], hy + rot(0, (TAG_H - HOLE_Y - 4) * s * z, th)[1]
        phi = self.swing(T - 0.14) * 1.2
        self._phi_rel = phi
        Lc = CHAIN * s * z
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

    # ------------------------------------------------------------------ receipt (мотив Money Brain)
    RC_W, RC_LH, RC_X, RC_SLOT = 340, 40, 1824, 176

    def receipt_plan(self):
        r = self.p.get("receipt")
        self.rc = r
        st = self.state.get("fd_receipt") or {}
        self.rc_prev = list(st.get("lines") or [])
        self.rc_was = bool(st.get("visible"))
        new = (r or {}).get("lines") or []
        self.rc_t = self.seq_times(new, 0.6) if r else []
        self.rc_new = [str(x.get("text", "")) for x in new] if r else []
        self.rc_all = self.rc_prev + self.rc_new
        self.rc_in = 0.0 if self.rc_was else self.at((r or {}).get("at"), 0.3)
        self.t_tear = self.at((r or {}).get("tear_at"), None) if r else None

    @functools.lru_cache(maxsize=32)
    def _paper(self, lines, hl, torn=False, zz=None):
        """Бумага чека: шапка, строки (новая — сверху, у щели принтера), зубчатый низ. lines — tuple, новые первыми.
        torn — оторван: верхний край тоже зубчатый; строка без «|» — итог крупнее по центру, без отточия.
        zz — масштаб отрисовки (оторванный чек крупнее — рисуем сразу в его размере, без апскейла)."""
        z = zz or self.z
        w, lh = int(self.RC_W * z), self.RC_LH * z
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
        dd.text((22 * z, y), "MONEY BRAIN · RECEIPT", font=f, fill=C("dim"))
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

    def receipt_setup(self):
        pass

    def draw_receipt(self, img, t, T, vd):
        if not self.rc:
            return
        z = self.z
        xo = self.gone(t, "receipt")
        a = (1 - xo) * vd
        if a <= 0.004:
            return
        x = self.RC_X * z - self.RC_W * z
        slot_y = self.RC_SLOT * z + M.bob(T, 2.4) * z * 0.5
        ka = 1.0 if self.rc_was else M.ease_out_expo(M.prog(t, self.rc_in, M.fr(M.F_APPEAR)))
        if ka <= 0:
            return
        # щель принтера
        d = ImageDraw.Draw(img, "RGBA")
        sw = (self.RC_W + 36) * z
        d.rounded_rectangle((x - 18 * z, slot_y - 12 * z, x - 18 * z + sw, slot_y + 4 * z), 8 * z,
                            fill=C("bg2", int(255 * ka * a)), outline=(255, 255, 255, int(40 * ka * a)), width=max(1, int(1.5 * z)))
        n_done = len(self.rc_prev) + sum(1 for x in self.rc_t if t >= x)
        cur = [i for i, x in enumerate(self.rc_t) if t >= x]
        last_t = self.rc_t[cur[-1]] if cur else None
        hl = last_t is not None and t < last_t + 1.6
        lines = tuple(reversed(self.rc_all[:n_done]))
        if self.t_tear is not None and t >= self.t_tear:
            self.draw_torn(img, t, lines, x, slot_y, a)
            return
        paper = self._paper(lines, hl)
        # подача: при новой строке бумага выезжает на одну строку; при первом появлении — целиком
        feed = 0.0
        if last_t is not None:
            feed = (1 - M.ease_out_expo(M.prog(t, last_t, 0.45))) * self.RC_LH * z
        if not self.rc_was:
            feed = max(feed, (1 - ka) * paper.height)
        vis = int(paper.height - feed)
        if vis <= 2:
            return
        crop = paper.crop((0, int(feed), paper.width, paper.height))
        max_h = int(880 * z - slot_y)
        if crop.height > max_h:
            crop = crop.crop((0, 0, crop.width, max_h))
            m = crop.getchannel("A")
            fade = Image.linear_gradient("L").resize((crop.width, int(120 * z))).transpose(Image.FLIP_TOP_BOTTOM)
            reg = m.crop((0, max_h - fade.height, crop.width, max_h))
            m.paste(Image.composite(reg, Image.new("L", reg.size, 0), fade), (0, max_h - fade.height))
            crop.putalpha(m)
        G.blit(img, crop, x, slot_y, a * ka)

    def draw_torn(self, img, t, lines, x, slot_y, a):
        """Чек оторван: рывок вниз (~0,15 с), затем выезжает в tear_to пружиной — крупно, с наклоном."""
        z = self.z
        to = self.rc.get("tear_to") or {}
        S = float(to.get("scale", 1.7))
        paper = self._paper(lines, True, True, z * S)
        x0, y0 = x + paper.width / S / 2, slot_y + paper.height / S / 2
        jerk = math.sin(math.pi * M.prog(t, self.t_tear, 0.16)) * 14 * z
        k = M.spring(M.prog(t, self.t_tear + 0.14, 0.9))
        x1, y1 = float(to.get("x", 960)) * z, float(to.get("y", 560)) * z
        cx, cy = M.lerp(x0, x1, k), M.lerp(y0, y1, k) + jerk
        sc = M.lerp(1.0, S, k) / S
        put(img, paper, cx, cy, a, sc, rot=M.lerp(0.0, float(to.get("rot", -4)), k), anchor="c")


# ===================================================================== icons (линейные, §9) — дополняют lab._li
import re  # noqa: E402

import studio.lab as _lab  # noqa: E402
from studio.lab import LabFullNumber  # noqa: E402

_li_base = _lab._li


def _li(name, d, s, c, w):
    m = s * 0.18
    if name == "wheel":  # колесо фортуны: обод, спицы, флажок-указатель сверху
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
        return _li_base(name, d, s, c, w)
    return True


_lab._li = _li


# ===================================================================== Full Number с разделителями тысяч
@template("fd_number",
          doc="lab_full_number ролика fake-discounts: то же, но числа ≥ 1000 с запятыми ($14,550) и опц. `decimals` "
              "(0,77 → 77¢ задавайте как value 77 + suffix ¢).",
          params=dict(LabFullNumber.PARAMS),
          beats=LabFullNumber.BEATS)
class FdNumber(LabFullNumber):
    def _spr(self, s, color):
        s = re.sub(r"\d{4,}", lambda m: f"{int(m.group(0)):,}", s)
        return super()._spr(s, color)
