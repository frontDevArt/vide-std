"""Пакет kit: timeline, steps, compare, map — история, процесс, сравнение, места (ROADMAP C4)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ... import gfx as G
from ...gfx import blit, blitc, eio, eo, eob, lerp, prog
from ..registry import P, template
from .base import SS, Ink, KitTemplate, circle


def _line(d, p0, p1, color, w):
    d.line((p0[0], p0[1], p1[0], p1[1]), fill=color, width=max(1, int(w)))


@template("timeline", aliases=("timeline",),
          doc="Лента времени: ось растёт от события к событию, точка выпрыгивает, дата и подпись поднимаются. "
              "В широком кадре ось горизонтальная (подписи сверху и снизу по очереди), в высоком — вертикальная.",
          params={"events": P([{"date": "2010", "text": "Событие"}], "события [{date, text, at}] (3–6)", list),
                  "first_beat": P(None, "событие i — на бите first_beat + i, если у него нет at", int),
                  **KitTemplate.COMMON},
          beats="событие — по `at` или биту first_beat + i (иначе равномерно); ось доходит до точки к её появлению")
class Timeline(KitTemplate):
    def setup(self):
        ev = self.p.get("events") or []
        self.n = n = len(ev)
        self.setup_title()
        self.tt = [self.item_at(e, i, n) for i, e in enumerate(ev)]
        self.horiz = not self.vert
        self.body = b = self.place(min(self.room(), self.area.h * (0.62 if self.horiz else 0.86)))
        cf, tf = self.fs(46), self.fs(32)
        if self.horiz:
            self.step = b.w / max(1, n)
            mw = int(self.step * 0.92)
            self.y = b.cy
            self.pos = [b.x0 + self.step * (i + 0.5) for i in range(n)]
        else:
            self.step = b.h / max(1, n)
            self.x = b.x0 + 46 * self.u
            mw = int(b.x1 - self.x - 50 * self.u)
            self.pos = [b.y0 + self.step * (i + 0.5) for i in range(n)]
        self.date = [G.text_sprite(str(e.get("date", "")), cf, "black", self.c, align="center" if self.horiz else "left",
                                   maxw=mw) for e in ev]
        self.txt = [G.text_sprite(str(e.get("text", "")), tf, "medium", "text", align="center" if self.horiz else "left",
                                  maxw=mw) for e in ev]
        self.dot = G.glowify(circle(int(30 * self.u), None, fill=self.style.col(self.c)), self.c, 8 * self.u)
        self.ring = circle(int(30 * self.u), None, outline=self.style.col(self.c), width=max(2, int(3 * self.u)))
        self.lw = max(2, int(4 * self.u))

    def reach(self, t):
        """Конец оси в координате вдоль неё: от точки к точке к появлению следующей."""
        b = self.body
        start = b.x0 if self.horiz else b.y0
        end = b.x1 if self.horiz else b.y1
        if not self.n:
            return start
        if t < self.tt[0]:
            return lerp(start, self.pos[0], eio(prog(t, self.tt[0] - 0.5, self.tt[0])))
        for i in range(1, self.n):
            if t < self.tt[i]:
                return lerp(self.pos[i - 1], self.pos[i], eio(prog(t, self.tt[i] - 0.45, self.tt[i])))
        return lerp(self.pos[-1], end, eio(prog(t, self.tt[-1], self.tt[-1] + 0.6)))

    def draw(self, img, t, T):
        a = self.fade(t)
        self.draw_title(img, t, a)
        b = self.body
        r = self.reach(t)
        dim, acc = self.style.col("dim", int(90 * a)), self.style.col(self.c, int(255 * a))
        with Ink(img) as d:
            if self.horiz:
                _line(d, (b.x0, self.y), (b.x1, self.y), dim, self.lw)
                if r > b.x0 + 1:
                    _line(d, (b.x0, self.y), (r, self.y), acc, self.lw)
            else:
                _line(d, (self.x, b.y0), (self.x, b.y1), dim, self.lw)
                if r > b.y0 + 1:
                    _line(d, (self.x, b.y0), (self.x, r), acc, self.lw)
        for i in range(self.n):
            k = prog(t, self.tt[i], self.tt[i] + 0.45)
            if k <= 0:
                continue
            p = self.pos[i]
            x, y = (p, self.y) if self.horiz else (self.x, p)
            blitc(img, self.dot, x, y, a, lerp(0.3, 1, eob(k)))
            rk = prog(t, self.tt[i], self.tt[i] + 0.7)
            if 0 < rk < 1:
                blitc(img, self.ring, x, y, (1 - rk) * a, 1 + 1.4 * rk)
            ds, ts = self.date[i], self.txt[i]
            ke = eo(k)
            if self.horiz:
                up = i % 2 == 0
                gap = 34 * self.u
                if up:
                    ty = y - gap - ts.height / 2
                    dy = ty - ts.height / 2 - ds.height / 2
                else:
                    dy = y + gap + ds.height / 2
                    ty = dy + ds.height / 2 + ts.height / 2
                off = (1 - ke) * 24 * self.u * (1 if up else -1)
                blitc(img, ds, x, dy + off, ke * a)
                blitc(img, ts, x, ty + off, ke * a)
            else:
                h = ds.height + ts.height
                x0 = x + 40 * self.u + (1 - ke) * 30 * self.u
                blit(img, ds, x0, y - h / 2, ke * a)
                blit(img, ts, x0, y - h / 2 + ds.height, ke * a)


@template("steps", aliases=("steps",),
          doc="Шаги процесса: номера в кружках, соединённые линией; шаг загорается по триггеру, пройденные остаются "
              "залитыми, линия к следующему растёт. В широком кадре — в ряд, в высоком — столбиком.",
          params={"steps": P([{"title": "Шаг", "text": "пояснение"}], "шаги [{title, text, at}] (2–5)", list),
                  "first_beat": P(None, "шаг i — на бите first_beat + i, если у него нет at", int),
                  **KitTemplate.COMMON},
          beats="шаг — по `at` или биту first_beat + i (иначе равномерно); текущий — с пульсирующим кольцом")
class Steps(KitTemplate):
    def setup(self):
        st = self.p.get("steps") or []
        self.n = n = len(st)
        self.setup_title()
        self.tt = [self.item_at(s, i, n) for i, s in enumerate(st)]
        self.row = not self.vert
        self.D0 = int(96 * self.u * self.kz)
        hf, tf = self.fs(42), self.fs(30)
        room = self.room()
        if self.row:
            self.step = self.area.w / max(1, n)
            mw = int(self.step * 0.9)
            al = "center"
        else:
            mw = int(self.area.w - self.D0 - 40 * self.u)
            al = "left"
        self.hd = [G.text_sprite(str(s.get("title", "")), hf, "black", "text", align=al, maxw=mw) for s in st]
        self.tx = [G.text_sprite(str(s.get("text", "")), tf, "medium", "dim", align=al, maxw=mw) if s.get("text") else None
                   for s in st]
        if self.row:
            th = max([h.height + (x.height if x is not None else 0) for h, x in zip(self.hd, self.tx)] or [0])
            self.body = b = self.place(min(room, self.D0 + 30 * self.u + th))
            self.cy = b.y0 + self.D0 / 2
            self.pos = [b.x0 + self.step * (i + 0.5) for i in range(n)]
        else:
            hs = [max(self.D0, h.height + (x.height if x is not None else 0)) for h, x in zip(self.hd, self.tx)]
            gap = min(80 * self.u, max(0.0, (room - sum(hs)) / max(1, n)))
            self.body = b = self.place(min(room, sum(hs) + gap * max(0, n - 1)))
            bw = self.D0 + 34 * self.u + max([max(h.width, x.width if x is not None else 0)
                                              for h, x in zip(self.hd, self.tx)] or [0])
            self.cx = b.x0 + max(0.0, (b.w - bw) / 2) + self.D0 / 2  # столбик — по центру зоны
            y, self.pos = b.y0, []
            for h in hs:
                self.pos.append(y + h / 2)
                y += h + gap
        self.off = circle(self.D0, None, outline=self.style.col("dim", 150), width=max(2, int(4 * self.u)))
        self.on = G.glowify(circle(self.D0, None, fill=self.style.col(self.c)), self.c, 12 * self.u)
        self.ring = circle(self.D0, None, outline=self.style.col(self.c), width=max(2, int(4 * self.u)))
        nf = int(self.D0 * 0.46)
        self.num_off = [G.text_sprite(str(i + 1), nf, "black", "dim") for i in range(n)]
        self.num_on = [G.text_sprite(str(i + 1), nf, "black", "bg_top") for i in range(n)]

    def center(self, i):
        return (self.pos[i], self.cy) if self.row else (self.cx, self.pos[i])

    def draw(self, img, t, T):
        a = self.fade(t)
        self.draw_title(img, t, a)
        ka = eo(prog(t, 0.0, 0.5)) * a
        lw = max(2, int(5 * self.u))
        R = self.D0 / 2 + 8 * self.u
        with Ink(img) as d:
            for i in range(self.n - 1):  # соединения: серые, к следующему шагу растёт цвет
                (x0, y0), (x1, y1) = self.center(i), self.center(i + 1)
                p0 = (x0 + R, y0) if self.row else (x0, y0 + R)
                p1 = (x1 - R, y1) if self.row else (x1, y1 - R)
                _line(d, p0, p1, self.style.col("dim", int(90 * ka)), lw)
                g = eio(prog(t, self.tt[i + 1] - 0.45, self.tt[i + 1]))
                if g > 0:
                    _line(d, p0, (lerp(p0[0], p1[0], g), lerp(p0[1], p1[1], g)), self.style.col(self.c, int(255 * a)), lw)
        cur = max([i for i in range(self.n) if t >= self.tt[i]] or [-1])
        for i in range(self.n):
            x, y = self.center(i)
            k = prog(t, self.tt[i], self.tt[i] + 0.4)
            blitc(img, self.off, x, y, ka * (1 - eo(k)))
            blitc(img, self.num_off[i], x, y, ka * (1 - eo(k)))
            if k > 0:
                done = i < cur
                blitc(img, self.on, x, y, a * (0.6 if done else 1.0), lerp(0.6, 1, eob(k)))
                blitc(img, self.num_on[i], x, y, a * eo(k))
                if i == cur:
                    pk = ((t - self.tt[i]) % 1.4) / 1.4
                    blitc(img, self.ring, x, y, a * (1 - pk) * 0.8, 1 + 0.35 * pk)
            kt = eo(prog(t, self.tt[i] - 0.15, self.tt[i] + 0.35))
            ta = (kt if i <= cur or k > 0 else 0.0) * a
            ta = max(ta, 0.45 * ka)  # будущие шаги видны приглушёнными
            hs, xs = self.hd[i], self.tx[i]
            if self.row:
                y0 = y + self.D0 / 2 + 24 * self.u
                blitc(img, hs, x, y0 + hs.height / 2, ta)
                if xs is not None:
                    blitc(img, xs, x, y0 + hs.height + xs.height / 2, ta)
            else:
                h = hs.height + (xs.height if xs is not None else 0)
                x0 = x + self.D0 / 2 + 34 * self.u
                blit(img, hs, x0, y - h / 2, ta)
                if xs is not None:
                    blit(img, xs, x0, y - h / 2 + hs.height, ta)


@template("compare", aliases=("compare",),
          doc="Сравнение двух вариантов по строкам: шапки колонок, в каждой строке подпись и два значения; "
              "победитель строки — цветом колонки и галочкой, проигравший приглушён.",
          params={"left": P({"title": "A", "color": "accent"}, "левая колонка {title, color}", dict),
                  "right": P({"title": "B", "color": "accent2"}, "правая колонка {title, color}", dict),
                  "rows": P([{"label": "Цена", "left": "$10", "right": "$15", "win": "left"}],
                            "строки [{label, left, right, win: left | right, at}] (2–5)", list),
                  "first_beat": P(None, "строка i — на бите first_beat + i, если у неё нет at", int),
                  **KitTemplate.COMMON},
          beats="шапки — сразу, строка — по `at` или биту first_beat + i (иначе равномерно)")
class Compare(KitTemplate):
    def setup(self):
        rows = self.p.get("rows") or []
        self.n = n = len(rows)
        self.setup_title()
        L, R = self.p.get("left") or {}, self.p.get("right") or {}
        self.cl, self.cr = L.get("color", "accent"), R.get("color", "accent2")
        a = self.area
        self.colw = a.w * (0.36 if self.vert else 0.3)
        self.xl, self.xr = a.x0 + self.colw / 2, a.x1 - self.colw / 2
        hf, vf = self.fs(46), self.fs(56)
        self.lf = self.fs(32)
        pw = int(self.colw)
        self.hl = self._pill(L.get("title", "A"), self.cl, pw, hf)
        self.hr = self._pill(R.get("title", "B"), self.cr, pw, hf)
        mid = int(a.w - 2 * self.colw - 30 * self.u) if not self.vert else int(a.w * 0.8)
        self.lab = [G.text_sprite(str(r.get("label", "")), self.lf, "semibold", "dim", maxw=mid) for r in rows]
        self.vl = [G.text_sprite(str(r.get("left", "")), vf, "black", "text", maxw=int(self.colw * 0.86)) for r in rows]
        self.vr = [G.text_sprite(str(r.get("right", "")), vf, "black", "text", maxw=int(self.colw * 0.86)) for r in rows]
        self.vl_w = [G.text_sprite(str(r.get("left", "")), vf, "black", self.cl, maxw=int(self.colw * 0.86)) for r in rows]
        self.vr_w = [G.text_sprite(str(r.get("right", "")), vf, "black", self.cr, maxw=int(self.colw * 0.86)) for r in rows]
        self.win = [r.get("win") for r in rows]
        self.tt = [self.item_at(r, i, n, start=0.6) for i, r in enumerate(rows)]
        ck = int(44 * self.u * self.kz)
        self.ck_l, self.ck_r = G.icon("check", ck, self.cl), G.icon("check", ck, self.cr)
        vh = max([s.height for s in self.vl + self.vr] or [0])
        lh = max([s.height for s in self.lab] or [0])
        self.rh = vh + (lh + 8 * self.u if self.vert else 0) + 40 * self.u
        head = self.hl.height + 30 * self.u
        self.body = b = self.place(min(self.room(), head + self.rh * n))
        self.hy = b.y0 + self.hl.height / 2
        self.r0 = b.y0 + head
        self.vh, self.lh = vh, lh

    def _pill(self, text, color, w, f):
        tx = G.text_sprite(str(text), f, "black", "bg_top", maxw=int(w * 0.9))
        p = G.rrect((w, int(tx.height + 24 * self.u)), int((tx.height + 24 * self.u) / 2), self.style.col(color))
        p.alpha_composite(tx, ((p.width - tx.width) // 2, (p.height - tx.height) // 2))
        return p

    def draw(self, img, t, T):
        a = self.fade(t)
        self.draw_title(img, t, a)
        k0 = eo(prog(t, 0.1, 0.55))
        blitc(img, self.hl, self.xl, self.hy + (1 - k0) * 20 * self.u, k0 * a)
        blitc(img, self.hr, self.xr, self.hy + (1 - k0) * 20 * self.u, k0 * a)
        with Ink(img) as d:
            cx = self.area.cx
            for i in range(self.n):
                k = eo(prog(t, self.tt[i], self.tt[i] + 0.45))
                if k <= 0:
                    continue
                y = self.r0 + self.rh * i
                if i:
                    d.line((self.area.x0, y, self.area.x1, y), fill=self.style.col("dim", int(60 * k * a)),
                           width=max(1, int(2 * self.u)))
                if self.vert:
                    ly = y + 20 * self.u + self.lh / 2
                    vy = ly + self.lh / 2 + 8 * self.u + self.vh / 2
                else:
                    ly = vy = y + self.rh / 2
                blitc(img, self.lab[i], cx, ly, k * a)
                w = self.win[i]
                win_k = eo(prog(t, self.tt[i] + 0.35, self.tt[i] + 0.8))
                for side, x, v, vw, ck in (("left", self.xl, self.vl[i], self.vl_w[i], self.ck_l),
                                           ("right", self.xr, self.vr[i], self.vr_w[i], self.ck_r)):
                    dx = (1 - k) * 40 * self.u * (-1 if side == "left" else 1)
                    lose = w in ("left", "right") and w != side
                    blitc(img, v, x + dx, vy, k * a * (1 - (0.55 * win_k if lose else 0)) * (1 - (win_k if w == side else 0)))
                    if w == side:
                        blitc(img, vw, x + dx, vy, k * a * win_k)
                        blitc(img, ck, x + dx + vw.width / 2 + ck.width * 0.55, vy, a * win_k, lerp(0.5, 1, eob(win_k)))


@template("map", aliases=("map",),
          doc="Карта-заглушка: точечная сетка-проекция (без контуров стран), булавки по широте/долготе с подписями, "
              "маршрут дугами от точки к точке. Для «где это было» и «откуда куда».",
          params={"pins": P([{"lat": 51.5, "lon": -0.1, "label": "London"}],
                            "булавки [{lat, lon, label, at}] (или x, y — доли кадра карты)", list),
                  "view": P(None, "область [lon0, lat0, lon1, lat1]; по умолчанию — вокруг булавок", list),
                  "route": P(False, "дуги между булавками по порядку"),
                  "pin_scale": P(1.0, "размер булавок и подписей (1,5–2 — крупно, для высокого кадра)"),
                  "first_beat": P(None, "булавка i — на бите first_beat + i, если у неё нет at", int),
                  **KitTemplate.COMMON},
          beats="булавка — по `at` или биту first_beat + i (иначе равномерно); дуга к ней рисуется перед её появлением")
class Map(KitTemplate):
    def setup(self):
        pins = self.p.get("pins") or []
        self.n = n = len(pins)
        self.setup_title()
        self.body = b = self.place(self.room())
        self.tt = [self.item_at(p, i, n, start=0.5) for i, p in enumerate(pins)]
        lon0, lat0, lon1, lat1 = self._fit(self._view(pins), b.w / max(1.0, b.h))
        aspect = max(0.5, (lon1 - lon0) / max(1e-6, lat1 - lat0))
        w = min(b.w, b.h * aspect)
        h = w / aspect
        self.m = type(b)(b.cx - w / 2, b.cy - h / 2, b.cx + w / 2, b.cy + h / 2)
        self.v = (lon0, lat0, lon1, lat1)

        def xy(p):
            if "x" in p and "y" in p:
                return self.m.x0 + self.m.w * float(p["x"]), self.m.y0 + self.m.h * float(p["y"])
            return (self.m.x0 + self.m.w * (float(p.get("lon", 0)) - lon0) / (lon1 - lon0),
                    self.m.y0 + self.m.h * (lat1 - float(p.get("lat", 0))) / (lat1 - lat0))
        self.pts = [xy(p) for p in pins]
        self.grid = self._grid()
        z = max(0.5, float(self.p.get("pin_scale", 1.0)))  # крупнее булавки — для высокого кадра и телефона
        self.pin = self._pin(int(40 * self.u * self.kz * z))
        self.ring = circle(int(36 * self.u * z), None, outline=self.style.col(self.c), width=max(2, int(3 * self.u * z)))
        lf = self.fs(32 * z)
        self.lab = [self._label(str(p.get("label", "")), lf) if p.get("label") else None for p in pins]
        self.dot = G.glowify(circle(int(16 * self.u), None, fill=self.style.col("text")), self.c, 6 * self.u)

    def _view(self, pins):
        v = self.p.get("view")
        if v and len(v) == 4:
            return tuple(float(x) for x in v)
        ll = [(float(p["lon"]), float(p["lat"])) for p in pins if "lon" in p and "lat" in p]
        if not ll:
            return -180.0, -60.0, 180.0, 80.0
        x0, x1 = min(x for x, _ in ll), max(x for x, _ in ll)
        y0, y1 = min(y for _, y in ll), max(y for _, y in ll)
        px, py = max(12.0, (x1 - x0) * 0.25), max(8.0, (y1 - y0) * 0.3)
        return max(-180.0, x0 - px), max(-80.0, y0 - py), min(180.0, x1 + px), min(85.0, y1 + py)

    @staticmethod
    def _fit(v, aspect):
        """Расширить область до пропорций кадра карты (равнопромежуточная проекция: градусы = пиксели)."""
        lon0, lat0, lon1, lat1 = v
        w, h = lon1 - lon0, lat1 - lat0
        if w / h > aspect:
            h2 = min(165.0, w / aspect)
            c = min(85 - h2 / 2, max(-80 + h2 / 2, (lat0 + lat1) / 2))
            lat0, lat1 = c - h2 / 2, c + h2 / 2
        else:
            w2 = min(360.0, h * aspect)
            c = min(180 - w2 / 2, max(-180 + w2 / 2, (lon0 + lon1) / 2))
            lon0, lon1 = c - w2 / 2, c + w2 / 2
        return lon0, lat0, lon1, lat1

    def _grid(self):
        """Точечная сетка и параллели/меридианы каждые 30° — один раз."""
        m = self.m
        img = Image.new("RGBA", (int(m.w) + 1, int(m.h) + 1), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        lon0, lat0, lon1, lat1 = self.v
        s = max(10.0, 22 * self.u)
        r = max(1.0, 2.2 * self.u)
        y = s / 2
        while y < m.h:
            x = s / 2
            while x < m.w:
                ex = 2 * (x / m.w) - 1  # виньетка: к краям слабее
                ey = 2 * (y / m.h) - 1
                al = int(95 * max(0.0, 1 - 0.55 * (ex * ex + ey * ey)))
                if al > 6:
                    d.ellipse((x - r, y - r, x + r, y + r), fill=self.style.col("dim", al))
                x += s
            y += s
        lw = max(1, int(2 * self.u))
        for g in range(-180, 181, 30):
            if lon0 < g < lon1:
                x = m.w * (g - lon0) / (lon1 - lon0)
                d.line((x, 0, x, m.h), fill=self.style.col(self.c, 40), width=lw)
        for g in range(-60, 81, 30):
            if lat0 < g < lat1:
                y = m.h * (lat1 - g) / (lat1 - lat0)
                d.line((0, y, m.w, y), fill=self.style.col(self.c, 40), width=lw)
        return img

    def _pin(self, s):
        S = s * SS
        img = Image.new("RGBA", (S, int(S * 1.4)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        c = self.style.col(self.c)
        d.ellipse((0, 0, S - 1, S - 1), fill=c)
        d.polygon([(S * 0.18, S * 0.72), (S * 0.82, S * 0.72), (S / 2, S * 1.38)], fill=c)
        o = S * 0.32
        d.ellipse((o, o, S - 1 - o, S - 1 - o), fill=self.style.col("bg_top"))
        return img.resize((s, int(s * 1.4)), Image.LANCZOS)

    def _label(self, text, f):
        tx = G.text_sprite(text, f, "bold", "text")
        pad = int(14 * self.u)
        p = G.rrect((tx.width + 2 * pad, tx.height + pad), int((tx.height + pad) / 2), self.style.col("panel", 225),
                    outline=self.style.col(self.c, 200), width=max(1, int(2 * self.u)))
        p.alpha_composite(tx, (pad, pad // 2))
        return p

    def arc(self, p0, p1, k):
        """Точки дуги от p0 к p1 (подъём — 18 % длины) до доли k."""
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        cx, cy = mx, my - 0.18 * L
        out = []
        for j in range(int(40 * k) + 1):
            s = k * j / max(1, int(40 * k))
            out.append(((1 - s) ** 2 * p0[0] + 2 * (1 - s) * s * cx + s * s * p1[0],
                        (1 - s) ** 2 * p0[1] + 2 * (1 - s) * s * cy + s * s * p1[1]))
        return out

    def draw(self, img, t, T):
        a = self.fade(t)
        self.draw_title(img, t, a)
        blit(img, self.grid, self.m.x0, self.m.y0, eo(prog(t, 0.0, 0.6)) * a)
        heads = []
        if self.p.get("route"):
            with Ink(img) as d:
                for i in range(1, self.n):
                    k = eio(prog(t, self.tt[i] - 0.7, self.tt[i]))
                    if k <= 0:
                        continue
                    pts = self.arc(self.pts[i - 1], self.pts[i], k)
                    if len(pts) > 1:
                        d.line(pts, fill=self.style.col(self.c, int(220 * a)), width=max(2, int(4 * self.u)), joint="curve")
                    if k < 1:
                        heads.append(pts[-1])
        for x, y in heads:  # точка на конце растущей дуги — поверх дуги
            blitc(img, self.dot, x, y, a)
        for i, (x, y) in enumerate(self.pts):
            k = prog(t, self.tt[i], self.tt[i] + 0.45)
            if k <= 0:
                continue
            rk = prog(t, self.tt[i], self.tt[i] + 0.8)
            if 0 < rk < 1:
                blitc(img, self.ring, x, y, (1 - rk) * a, 1 + 2 * rk)
            drop = (1 - eob(k)) * 40 * self.u
            blitc(img, self.pin, x, y - self.pin.height / 2 + self.pin.height * 0.02 - drop, eo(k) * a)
            lb = self.lab[i]
            if lb is not None:
                kl = eo(prog(t, self.tt[i] + 0.15, self.tt[i] + 0.55))
                left = x + self.pin.width * 0.7 + lb.width > self.area.x1
                lx = x - self.pin.width * 0.7 - lb.width if left else x + self.pin.width * 0.7
                lx = max(self.area.x0, min(self.area.x1 - lb.width, lx))
                ly = max(self.area.y0, y - self.pin.height * 0.75 - lb.height / 2)
                blit(img, lb, lx, ly, kl * a)

