"""Пакет kit: chart — столбики, линия или круг из CSV (assets/…) или из значений в сценарии (ROADMAP C4, тип data-story)."""
from __future__ import annotations

import csv
import io
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw

from ... import assets as AS
from ... import gfx as G
from ...gfx import blit, blitc, eio, eo, eob, lerp, prog
from ..registry import AT, NUM, P, template
from .base import SS, Ink, KitTemplate, number

_NUM = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")
SERIES = ("accent", "lime", "amber", "violet", "red", "magenta")  # доли круга; accent2 — у выделенной


def parse_number(s):
    """'$1,234.5' | '12 %' | '3,5' (запятая — дробная, если нет точки и после неё не 3 цифры) → float или None."""
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    s = str(s or "").strip().replace(" ", "").replace(" ", "")
    if "," in s and "." not in s and not re.search(r",\d{3}(?!\d)", s):
        s = s.replace(",", ".")
    s = s.replace(",", "")
    m = _NUM.search(s)
    return float(m.group()) if m else None


def decimals_of(cells):
    """Знаков после точки в данных (наибольшее, не больше 2)."""
    out = 0
    for c in cells:
        s = str(c).strip()
        if "." in s and not isinstance(c, int):
            out = max(out, len(re.sub(r"\D", "", s.rsplit(".", 1)[1])))
    return min(out, 2)


def read_csv(path, x=None, y=None):
    """CSV → (подписи, значения, знаков после точки, имя столбца значений). Разделитель — , ; или таб; первая строка —
    заголовки. x/y — имена столбцов (по умолчанию первый и второй); строки без числа пропускаются."""
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [r for r in csv.reader(io.StringIO(text), dialect) if any(c.strip() for c in r)]
    if len(rows) < 2:
        raise ValueError(f"{path}: нужна строка заголовков и хотя бы одна строка данных")
    head = [h.strip() for h in rows[0]]

    def col(name, default):
        if name is None:
            return default
        if name not in head:
            raise ValueError(f"{path}: нет столбца '{name}' (есть: {', '.join(head)})")
        return head.index(name)
    xi, yi = col(x, 0), col(y, 1 if len(head) > 1 else 0)
    labels, values, raw = [], [], []
    for r in rows[1:]:
        if max(xi, yi) >= len(r):
            continue
        v = parse_number(r[yi])
        if v is None:
            continue
        labels.append(r[xi].strip())
        values.append(v)
        raw.append(r[yi].strip())
    return labels, values, decimals_of(raw), head[yi]


def series(p, roots):
    """Данные сцены: values в сценарии или CSV из data → (подписи, значения, знаков после точки)."""
    vals = p.get("values")
    if vals:
        labels, values = [], []
        for i, v in enumerate(vals):
            if isinstance(v, dict):
                labels.append(str(v.get("label", i + 1)))
                values.append(parse_number(v.get("value")) or 0.0)
            else:
                labels.append(str(i + 1))
                values.append(parse_number(v) or 0.0)
        return labels, values, decimals_of([v.get("value") if isinstance(v, dict) else v for v in vals])
    if p.get("data"):
        labels, values, dec, _ = read_csv(AS.path(roots, p["data"]), p.get("x"), p.get("y"))
        return labels, values, dec
    return ["A", "B", "C"], [3.0, 5.0, 4.0], 0


@template("chart", aliases=("chart",),
          doc="График из данных: столбики (bar), линия (line) или круг (pie). Данные — CSV в assets/ (data, столбцы x/y) "
              "или values прямо в сценарии. Значения растут и набегают числами; выделенное — цветом accent2. "
              "В высоком кадре столбики лежат (подписи слева), в широком стоят.",
          params={"type": P("bar", "bar | line | pie"),
                  "data": P(None, "CSV (первая строка — заголовки), путь от папки проекта: assets/data.csv; "
                                  "файл — в assets.yaml с источником", str),
                  "x": P(None, "столбец подписей (по умолчанию первый)", str),
                  "y": P(None, "столбец значений (по умолчанию второй)", str),
                  "values": P(None, "данные в сценарии вместо CSV: [{label, value}] или [числа]", list),
                  "prefix": P("", "перед числом ($)"), "suffix": P("", "после числа (%, h, k)"),
                  "decimals": P(None, "знаков после точки (по умолчанию — как в данных)", int),
                  "highlight": P(None, "выделить: подпись или номер с 0 (цвет accent2)", (str, int)),
                  "max": P(None, "верх шкалы (по умолчанию — максимум данных)", NUM),
                  "at": P(0, "начало роста: бит | '1.5s' | слово озвучки", AT),
                  "grow": P(1.6, "секунд на рост всех значений", NUM),
                  "first_beat": P(None, "значение i — на бите first_beat + i (вместо общего роста)", int),
                  "source": P(None, "подпись источника под графиком", str),
                  **KitTemplate.COMMON},
          beats="рост — с `at` за `grow` секунд; при first_beat — по значению на бит; выделенное значение вспыхивает "
                "в конце роста")
class Chart(KitTemplate):
    def setup(self):
        self.kind = self.p.get("type", "bar")
        self.labels, self.values, dec = series(self.p, self.roots)
        self.dec = int(self.p["decimals"]) if self.p.get("decimals") is not None else dec
        self.n = len(self.values)
        hl = self.p.get("highlight")
        self.hl = (hl if isinstance(hl, int) else self.labels.index(hl) if hl in self.labels else None)
        self.vmax = float(self.p.get("max") or max(self.values + [0.0]) or 1.0)
        self.vmin = min(0.0, min(self.values + [0.0]))
        self.setup_title()
        self.src = (G.text_sprite(self.p["source"], self.fs(30), "medium", "dim", maxw=int(self.area.w * 0.9))
                    if self.p.get("source") else None)
        self.t0 = self.at(self.p.get("at", 0), 0.3)
        g = float(self.p.get("grow", 1.6))
        # время каждого значения: [начало, конец] роста
        if self.p.get("first_beat") is not None:
            self.tt = [(t, t + 0.6) for t in (self.item_at({}, i, self.n) for i in range(self.n))]
        else:
            st = g * 0.35 / max(1, self.n - 1)
            self.tt = [(self.t0 + i * st, self.t0 + i * st + g * 0.65) for i in range(self.n)]
        src_h = self.src.height + int(16 * self.u) if self.src is not None else 0
        self.body = self.place(min(self.room(), self.area.h * (0.86 if self.vert else 0.9)))
        self.plot = type(self.body)(self.body.x0, self.body.y0, self.body.x1, self.body.y1 - src_h)
        {"bar": self.setup_bar, "line": self.setup_line, "pie": self.setup_pie}.get(self.kind, self.setup_bar)()

    def color(self, i):
        if self.kind == "pie":
            return SERIES[i % len(SERIES)] if i != self.hl else "accent2"
        return "accent2" if i == self.hl else self.c

    def fmt(self, v):
        return number(v, self.dec, self.p.get("prefix", ""), self.p.get("suffix", ""))

    def grown(self, i, t):
        a, b = self.tt[i]
        return eio(prog(t, a, b))

    # ------------------------------------------------------------------ bar
    def setup_bar(self):
        b = self.plot
        self.lying = self.vert
        f = self.fs(34 if self.n <= 6 else 28)
        if self.lying:  # высокий кадр: строки «подпись | полоса | число»
            self.lbl = [G.text_sprite(s, f, "semibold", "text", align="right", maxw=int(b.w * 0.3)) for s in self.labels]
            self.lw = max(s.width for s in self.lbl) if self.lbl else 0
            self.row = b.h / max(1, self.n)
            self.bh = min(self.row * 0.62, 84 * self.u)
        else:
            self.lbl = [G.text_sprite(s, f, "semibold", "text", maxw=int(b.w / max(1, self.n) * 0.96)) for s in self.labels]
            self.col_w = b.w / max(1, self.n)
            self.bw = min(self.col_w * 0.6, 170 * self.u)
            self.lh = max([s.height for s in self.lbl] or [0])
        self.vf = self.fs(40 if self.n <= 6 else 32)

    def draw_bar(self, img, t, a):
        b = self.plot
        with Ink(img) as d:
            r = int(10 * self.u)
            span = self.vmax - self.vmin or 1.0
            for i, v in enumerate(self.values):
                k = self.grown(i, t)
                if k <= 0 and t < self.tt[i][0] - 0.3:
                    continue
                ka = eo(prog(t, self.tt[i][0] - 0.3, self.tt[i][0])) * a
                c = self.color(i)
                fill = self.style.col(c, int(235 * ka))
                vs = G.text_sprite(self.fmt(v * k), self.vf, "black", c if i == self.hl else "text")
                if self.lying:
                    cy = b.y0 + self.row * (i + 0.5)
                    blit(img, self.lbl[i], b.x0 + self.lw - self.lbl[i].width, cy - self.lbl[i].height / 2, ka)
                    x0 = b.x0 + self.lw + 18 * self.u
                    full = b.x1 - x0 - vs.width - 24 * self.u
                    L = full * (v - self.vmin) / span * k
                    if L > 2:
                        d.rounded_rectangle((x0, cy - self.bh / 2, x0 + L, cy + self.bh / 2), min(r, L / 2), fill=fill)
                    blit(img, vs, x0 + max(L, 0) + 14 * self.u, cy - vs.height / 2, ka)
                else:
                    cx = b.x0 + self.col_w * (i + 0.5)
                    base = b.y1 - self.lh - 14 * self.u
                    full = base - b.y0 - vs.height - 14 * self.u
                    L = full * (v - self.vmin) / span * k
                    blitc(img, self.lbl[i], cx, base + 14 * self.u + self.lh / 2, ka)
                    if L > 2:
                        d.rounded_rectangle((cx - self.bw / 2, base - L, cx + self.bw / 2, base), min(r, L / 2), fill=fill)
                    blitc(img, vs, cx, base - max(L, 0) - 10 * self.u - vs.height / 2, ka)
                if i == self.hl:  # вспышка выделенного в конце роста
                    fk = prog(t, self.tt[i][1] - 0.1, self.tt[i][1] + 0.5)
                    if 0 < fk < 1:
                        if self.lying:
                            box = (x0 - 6 * self.u, cy - self.bh / 2 - 6 * self.u, x0 + L + 6 * self.u, cy + self.bh / 2 + 6 * self.u)
                        else:
                            box = (cx - self.bw / 2 - 6 * self.u, base - L - 6 * self.u, cx + self.bw / 2 + 6 * self.u, base + 2)
                        d.rounded_rectangle(box, r + 6 * self.u, outline=self.style.col(c, int(255 * (1 - fk) * a)),
                                            width=max(2, int(5 * self.u)))
            if not self.lying:  # ось
                base = b.y1 - self.lh - 14 * self.u
                w = (b.w - self.col_w * 0.2) * eo(prog(t, self.t0 - 0.4, self.t0 + 0.2))
                if w > 2:
                    d.line((b.cx - w / 2, base, b.cx + w / 2, base), fill=self.style.col("dim", int(160 * a)),
                           width=max(2, int(3 * self.u)))

    # ------------------------------------------------------------------ line
    def setup_line(self):
        b = self.plot
        f = self.fs(30)
        every = max(1, math.ceil(self.n / (8 if not self.vert else 5)))
        self.xl = [G.text_sprite(s, f, "semibold", "dim") if i % every == 0 or i == self.n - 1 else None
                   for i, s in enumerate(self.labels)]
        lh = max([s.height for s in self.xl if s is not None] or [0])
        self.vf = self.fs(36)
        top = self.vf * 1.4
        pad = max([s.width for s in self.xl if s is not None] or [0]) / 2 + 8 * self.u
        self.box = type(b)(b.x0 + pad, b.y0 + top, b.x1 - pad, b.y1 - lh - 18 * self.u)
        self.xl_y = b.y1 - lh / 2
        span = self.vmax - self.vmin or 1.0
        bx = self.box
        self.pts = [(bx.x0 + bx.w * (i / max(1, self.n - 1)), bx.y1 - bx.h * (v - self.vmin) / span)
                    for i, v in enumerate(self.values)]
        # линия и заливка под ней — один раз, с суперсэмплингом; в кадре — обрезка по ходу роста
        W, H = int(b.w) + 2, int(b.h) + 2
        ox, oy = b.x0, b.y0
        big = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        dd = ImageDraw.Draw(big)
        pp = [((x - ox) * SS, (y - oy) * SS) for x, y in self.pts]
        if len(pp) > 1:
            dd.polygon(pp + [(pp[-1][0], (bx.y1 - oy) * SS), (pp[0][0], (bx.y1 - oy) * SS)],
                       fill=self.style.col(self.c, 46))
            dd.line(pp, fill=self.style.col(self.c), width=int(7 * self.u * SS), joint="curve")
        self.lay = big.resize((W, H), Image.LANCZOS)
        self.lay_glow = G.glowify(self.lay, self.c, 10 * self.u, 0.7)
        self.gpad = (self.lay_glow.width - W) // 2
        grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(grid)
        for j in range(4):
            y = bx.y1 - bx.h * j / 3 - oy
            gd.line((bx.x0 - ox, y, bx.x1 - ox, y), fill=self.style.col("dim", 70 if j else 150), width=max(1, int(2 * self.u)))
        self.grid = grid
        self.dot = G.glowify(G.rrect((int(22 * self.u),) * 2, int(11 * self.u), self.style.col("text")), self.c, 8 * self.u)
        self.tick = G.rrect((int(14 * self.u),) * 2, int(7 * self.u), self.style.col(self.c))

    def ptimes(self):
        """Время, когда линия доходит до точки i: по битам (first_beat) или равномерно за grow."""
        if self.p.get("first_beat") is not None:
            return [a for a, _ in self.tt]
        a, b = self.tt[0][0], self.tt[-1][1]
        return [lerp(a, b, i / max(1, self.n - 1)) for i in range(self.n)]

    def head(self, t):
        """(доля пути по x, индекс последней пройденной точки; −1 — линия ещё не началась)."""
        pt = self.ptimes()
        if t < pt[0]:
            return 0.0, -1
        if self.n < 2:
            return 1.0, 0
        for i in range(self.n - 1):
            if t < pt[i + 1]:
                return (i + eio(prog(t, pt[i], pt[i + 1]))) / (self.n - 1), i
        return 1.0, self.n - 1

    def draw_line(self, img, t, a):
        b = self.plot
        ga = eo(prog(t, self.t0 - 0.5, self.t0)) * a
        blit(img, self.grid, b.x0, b.y0, ga)
        for i, s in enumerate(self.xl):
            if s is not None:
                blitc(img, s, self.pts[i][0], self.xl_y, ga)
        frac, last = self.head(t)
        if last < 0:
            return
        bx = self.box
        x = bx.x0 + bx.w * frac
        cut = int(x - b.x0 + 2)
        if cut > 0:
            g = self.lay_glow.crop((0, 0, min(self.lay_glow.width, cut + self.gpad), self.lay_glow.height))
            blit(img, g, b.x0 - self.gpad, b.y0 - self.gpad, a)
        for i in range(last + 1):
            px, py = self.pts[i]
            blitc(img, self.tick, px, py, a)
            show = self.n <= 7 or i in (0, self.n - 1, self.hl)
            if show:
                k = eo(prog(t, self.ptimes()[i], self.ptimes()[i] + 0.3))
                c = self.color(i)
                vs = G.text_sprite(self.fmt(self.values[i]), self.vf if i != self.hl else int(self.vf * 1.2), "black",
                                   c if i == self.hl else "text")
                blitc(img, vs, px, py - vs.height / 2 - 14 * self.u, a * k)
        # голова линии
        i = min(self.n - 2, max(0, int(frac * (self.n - 1)))) if self.n > 1 else 0
        if self.n > 1 and frac < 1:
            f = frac * (self.n - 1) - i
            hx, hy = lerp(self.pts[i][0], self.pts[i + 1][0], f), lerp(self.pts[i][1], self.pts[i + 1][1], f)
            blitc(img, self.dot, hx, hy, a)

    # ------------------------------------------------------------------ pie
    def setup_pie(self):
        b = self.plot
        tot = sum(max(0.0, v) for v in self.values) or 1.0
        self.share = [max(0.0, v) / tot for v in self.values]
        f = self.fs(32)
        self.leg = [G.text_sprite(f"{s}  ·  {round(sh * 100)}%", f, "semibold", "text", align="left",
                                  maxw=int(b.w * (0.8 if self.vert else 0.42))) for s, sh in zip(self.labels, self.share)]
        lh = max([s.height for s in self.leg] or [0]) * 1.25
        if self.vert:
            legend_h = lh * self.n
            self.R = int(min(b.w * 0.36, (b.h - legend_h - 30 * self.u) / 2))
            self.pc = (b.cx, b.y0 + self.R)
            lw = max([s.width for s in self.leg] or [0]) + 50 * self.u
            self.lx, self.ly, self.lh = b.cx - lw / 2, b.y0 + 2 * self.R + 30 * self.u + lh / 2, lh
        else:
            self.R = int(min(b.h / 2, b.w * 0.24))
            self.pc = (b.x0 + b.w * 0.3, b.cy)
            self.lx, self.lh = b.x0 + b.w * 0.56, lh
            self.ly = b.cy - lh * (self.n - 1) / 2
        self.sw = int(self.R * 0.36)  # толщина кольца
        self.swatch = [G.rrect((int(26 * self.u),) * 2, int(7 * self.u), self.style.col(self.color(i))) for i in range(self.n)]
        sh = self.share[self.hl] if self.hl is not None else None
        self.center = (f"{round(sh * 100)}%" if sh is not None else self.fmt(sum(self.values)))
        self.cf = int(self.R * 0.3)
        hole = 2 * (self.R - self.sw) * 0.62  # число в центре не шире дырки кольца
        w = G.text_sprite(self.center, self.cf, "black", "text").width
        if w > hole:
            self.cf = max(8, int(self.cf * hole / w))
        self._done = None

    def ring(self, t):
        if self._done is not None and t >= self.tt[-1][1]:
            return self._done
        D = self.R * 2
        S = D * 2
        big = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        a0 = -90.0
        for i, sh in enumerate(self.share):
            k = self.grown(i, t) if self.p.get("first_beat") is not None else 1.0
            span = 360 * sh
            if self.p.get("first_beat") is None:  # общий рост — круг заполняется по часовой
                g = eio(prog(t, self.tt[0][0], self.tt[-1][1])) * 360
                span = max(0.0, min(span, g - (a0 + 90)))
            else:
                span *= k
            if span > 0.2:
                d.pieslice((0, 0, S - 1, S - 1), a0, a0 + span, fill=self.style.col(self.color(i)))
            a0 += 360 * sh
        hole = int(2 * (self.R - self.sw))
        o = (S - hole) // 2
        d.ellipse((o, o, o + hole - 1, o + hole - 1), fill=(0, 0, 0, 0))
        out = big.resize((D, D), Image.LANCZOS)
        if t >= self.tt[-1][1]:
            self._done = out
        return out

    def draw_pie(self, img, t, a):
        cx, cy = self.pc
        D = self.R * 2
        track = getattr(self, "_track", None)
        if track is None:
            track = Image.new("RGBA", (D * 2, D * 2), (0, 0, 0, 0))
            dd = ImageDraw.Draw(track)
            dd.ellipse((0, 0, D * 2 - 1, D * 2 - 1), fill=self.style.col("dim", 50))
            o = 2 * self.sw
            dd.ellipse((o, o, D * 2 - 1 - o, D * 2 - 1 - o), fill=(0, 0, 0, 0))
            self._track = track = track.resize((D, D), Image.LANCZOS)
        ka = eo(prog(t, self.t0 - 0.5, self.t0)) * a
        blitc(img, track, cx, cy, ka)
        blitc(img, self.ring(t), cx, cy, a)
        kc = eo(prog(t, self.tt[-1][1] - 0.4, self.tt[-1][1] + 0.2))
        if kc > 0:
            c = "accent2" if self.hl is not None else "text"
            blitc(img, G.text_sprite(self.center, self.cf, "black", c), cx, cy, kc * a, lerp(0.8, 1, eob(kc)))
        for i, s in enumerate(self.leg):
            k = eo(prog(t, self.tt[i][0], self.tt[i][0] + 0.4))
            if k <= 0:
                continue
            y = self.ly + i * self.lh
            dx = (1 - k) * 30 * self.u
            blitc(img, self.swatch[i], self.lx + 13 * self.u + dx, y, k * a)
            blit(img, s, self.lx + 40 * self.u + dx, y - s.height / 2, k * a)

    # ------------------------------------------------------------------ кадр
    def draw(self, img, t, T):
        a = self.fade(t)
        self.draw_title(img, t, a)
        {"bar": self.draw_bar, "line": self.draw_line, "pie": self.draw_pie}.get(self.kind, self.draw_bar)(img, t, a)
        if self.src is not None:
            k = eo(prog(t, self.t0, self.t0 + 0.5))
            blitc(img, self.src, self.area.cx, self.body.y1 - self.src.height / 2, k * a * 0.9)

