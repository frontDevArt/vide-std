"""Свои элементы ролика «money-changes-you» (STYLE §14, новые элементы): пульт личности и лупа.

Шаблон `lab_mixer` — Center Diagram: микшер с мастер-фейдером INCOME (accent) и пятью фейдерами личности O · C · E · A · N.
Фейдеры едут по словам-триггерам (`moves`); сдвиги черт в ролике крошечные — их видно только в «лупе» (`lens`):
круглое увеличение рядом с фейдером, где призрак «до» (dim) и ручка «после» (accent-2) разнесены в N раз.
Слева может печататься расчётный лист (`slip`) — строки по триггерам, последняя обычно RAISE.
Через склейку (SCENE_SPEC: только state): положение всех фейдеров и пульта (`mc_mixer`), если в `keep` есть `mixer`
и у следующей сцены `mixer.from_prev: true`.
Координаты — дизайн-пиксели 1920×1080, масштаб self.z; высокий кадр — пульт по центру рамки self.area, лист и лупа под ним.
"""
from __future__ import annotations

import functools

from PIL import ImageDraw

from studio import gfx as G
from studio import motion as M
from studio.lab import C, LabTemplate, SS, _down, _ss_canvas, glass, put, txt
from studio.templates import template

CH = ["INCOME", "O", "C", "E", "A", "N"]   # каналы пульта: мастер + Big Five
STEP = 150                                  # шаг каналов (дизайн-px)
TRACK = 440                                 # длина дорожки фейдера
KW, KH = 84, 34                             # ручка фейдера
PAD_X, PAD_TOP, PAD_BOT = 40, 70, 110       # поля корпуса пульта
LENS_R = 165                                # радиус лупы
MOVE = 0.9                                  # переезд фейдера, с
STATE = "mc_mixer"


# ===================================================================== sprites
@functools.lru_cache(maxsize=4)
def panel_sprite(z):
    """Корпус пульта: стеклянная карточка + дорожки с делениями + подписи каналов."""
    w = int((len(CH) * STEP + 2 * PAD_X) * z)
    h = int((TRACK + PAD_TOP + PAD_BOT) * z)
    card = glass(w, h, int(22 * z)).copy()
    img, d = _ss_canvas(w, h)
    k = SS * z
    for i, name in enumerate(CH):
        cx = (PAD_X + STEP * (i + 0.5)) * k
        y0, y1 = PAD_TOP * k, (PAD_TOP + TRACK) * k
        d.rounded_rectangle((cx - 5 * k, y0, cx + 5 * k, y1), 5 * k, fill=(0, 0, 0, 150), outline=(255, 255, 255, 40), width=int(1.5 * k))
        for j in range(11):
            y = y0 + (y1 - y0) * j / 10
            ln = (22 if j % 5 == 0 else 12) * k
            d.line((cx - 30 * k - ln, y, cx - 30 * k, y), fill=(255, 255, 255, 60 if j % 5 else 110), width=int(2 * k))
    if True:   # разделитель мастер | черты
        x = (PAD_X + STEP) * k
        d.line((x, PAD_TOP * k, x, (PAD_TOP + TRACK) * k), fill=(255, 255, 255, 34), width=int(2 * k))
    card.alpha_composite(_down(img, w, h))
    for i, name in enumerate(CH):
        col = "accent" if i == 0 else "text"
        t = txt(name, (20 if i == 0 else 30) * z, "bold" if i else "medium", col, "mono" if i == 0 else "head", 0.06)
        cx = (PAD_X + STEP * (i + 0.5)) * z
        card.alpha_composite(t, (int(cx - t.width / 2), int((PAD_TOP + TRACK + 40) * z)))
    return card


@functools.lru_cache(maxsize=8)
def knob_sprite(z, color, ghost=False):
    w, h = int(KW * z), int(KH * z)
    img, d = _ss_canvas(w, h)
    k = SS * z
    if ghost:
        d.rounded_rectangle((k, k, w * SS - k, h * SS - k), 8 * k, outline=C("dim", 200), width=int(3 * k))
    else:
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 8 * k, fill=C(color, 235) if color != "bg2" else C("bg2", 250),
                            outline=(255, 255, 255, 90), width=int(1.5 * k))
        d.line((10 * k, h * SS / 2, w * SS - 10 * k, h * SS / 2), fill=(10, 13, 20, 200) if color != "bg2" else C("text", 200),
               width=int(3 * k))
    return _down(img, w, h)


@functools.lru_cache(maxsize=4)
def lens_sprite(z):
    """Лупа: тёмный круг, кольцо accent-2, ручка-«держатель» снизу справа."""
    r = int(LENS_R * z)
    w = h = 2 * r + int(80 * z)
    img, d = _ss_canvas(w, h)
    k = SS * z
    c = (r + 10 * z) * SS
    d.line((c + r * SS * 0.72, c + r * SS * 0.72, c + (r + 60 * z) * SS, c + (r + 60 * z) * SS), fill=C("accent2", 230), width=int(16 * k))
    d.ellipse((c - r * SS, c - r * SS, c + r * SS, c + r * SS), fill=C("bg", 245), outline=C("accent2", 255), width=int(6 * k))
    return _down(img, w, h), int(r + 10 * z)


# ===================================================================== template
@template("lab_mixer",
          doc="lab · Center Diagram ролика money-changes-you: пульт личности — мастер INCOME + фейдеры O C E A N. "
              "Фейдеры едут по `moves` ({ch, to, at}); `lens` — лупа над фейдером ({ch, at, shift, shift_at, text, zoom}), "
              "где сдвиг виден увеличенным; `slip` — расчётный лист слева ({title, at, rows:[{text, value, at, color}]}). "
              "Пульт переходит через склейку (keep: [mixer] + mixer.from_prev).",
          params={"mixer": {"at": 0, "from_prev": False, "x": 960,
                            "values": {"INCOME": 0.3, "O": 0.5, "C": 0.5, "E": 0.5, "A": 0.5, "N": 0.5}},
                  "moves": [{"ch": "INCOME", "to": 0.85, "at": None}],
                  "lens": {"ch": "C", "at": None, "shift": 60, "shift_at": None, "text": "+0.06 SD", "zoom": "×20"},
                  "slip": {"title": "PAYSLIP", "at": None, "rows": [{"text": "BASE", "value": "100%", "at": None}]},
                  "highlight": None,
                  "focus": [{"ch": "O", "at": None}],
                  **LabTemplate.COMMON},
          beats="всё по словам-триггерам `at`; moves[i].to — положение 0..1, переезд 0,9 с; lens.shift — сдвиг в лупе, px")
class LabMixer(LabTemplate):
    # ------------------------------------------------------------------ plan
    def plan_body(self):
        p = self.p
        prev = self.state.get(STATE) or {}
        mx = p.get("mixer") or {}
        self.carry = bool(mx.get("from_prev")) and bool(prev)
        base = {c: 0.5 for c in CH}
        base["INCOME"] = 0.3
        if self.carry:
            base.update(prev.get("values") or {})
        else:
            base.update(mx.get("values") or {})
        self.v0 = {c: float(base[c]) for c in CH}
        self.x_to = float(mx.get("x", 960))
        self.x_from = float(prev.get("x", self.x_to)) if self.carry else self.x_to
        self.t_mix = -10.0 if self.carry else self.at(mx.get("at"), 0.2)
        self.moves = {c: [] for c in CH}
        cur = dict(self.v0)
        for i, mv in enumerate(p.get("moves") or []):
            c = str(mv.get("ch", "INCOME")).upper()
            if c not in cur:
                print(f"  ⚠️  lab_mixer: канал «{c}» не найден (есть {', '.join(CH)})")
                continue
            t0 = self.at(mv.get("at"), 0.8 + 1.0 * i)
            to = float(mv.get("to", cur[c]))
            self.moves[c].append((t0, cur[c], to))
            cur[c] = to
        self.v_end = cur
        ln = p.get("lens")
        self.lens = ln
        if ln:
            self.l_ch = str(ln.get("ch", "C")).upper()
            self.t_lens = self.at(ln.get("at"), 1.2)
            self.t_shift = self.at(ln.get("shift_at"), self.t_lens + 0.6)
        sl = p.get("slip")
        self.slip = sl
        if sl:
            self.t_slip = self.at(sl.get("at"), 0.2)
            self.slip_rows = sl.get("rows") or []
            self.t_rows = self.seq_times(self.slip_rows, self.t_slip + 0.4)
        self.hl = str(p.get("highlight")).upper() if p.get("highlight") else (self.l_ch if ln else None)
        fc = p.get("focus") or []   # подсветка фейдеров по очереди: [{ch, at}] — горит последний наступивший
        self.focus = [(t0, str(f.get("ch", "")).upper()) for f, t0 in zip(fc, self.seq_times(fc, 0.8))]

    def state_out(self):
        out = super().state_out()
        out[STATE] = {"values": self.v_end, "x": self.x_to} if "mixer" in self.keep else None
        return out

    def sfx_body(self):
        ev = [] if self.carry else [(self.t_mix, "pop")]
        for c in CH:
            for t0, a, b in self.moves[c]:
                if abs(b - a) > 0.05:
                    ev.append((t0, "swish"))
                    ev += self.ticks(t0 + 0.1, MOVE * 0.8)
        if self.lens:
            ev += [(self.t_lens, "pop"), (self.t_shift, "swish")]
        if self.slip:
            ev += [(self.t_slip, "pop")] + [(x, "tick") for x in self.t_rows]
        return ev

    # ------------------------------------------------------------------ setup
    def setup_body(self):
        z = self.z
        self.panel = panel_sprite(z)
        self.knob = {"master": knob_sprite(z, "accent"), "trait": knob_sprite(z, "bg2"),
                     "hl": knob_sprite(z, "accent2"), "ghost": knob_sprite(z, "dim", True)}
        if self.lens:
            self.lens_spr, self.lens_c = lens_sprite(z)
            self.lens_txt = G.text_sprite(str(self.lens.get("text", "")), int(46 * z), "bold", "accent2", family="head")
            self.lens_zoom = txt(str(self.lens.get("zoom", "")), 20 * z, "medium", "dim", "mono", 0.06)
            self.lens_big = {"ghost": knob_sprite(z * 1.6, "dim", True), "hl": knob_sprite(z * 1.6, "accent2")}
        if self.slip:
            w, h = int(470 * z), int((150 + 86 * len(self.slip_rows)) * z)
            self.slip_card = glass(w, h, int(18 * z)).copy()
            t = txt(str(self.slip.get("title", "PAYSLIP")).upper(), 20 * z, "medium", "dim", "mono", 0.12)
            self.slip_card.alpha_composite(t, (int(36 * z), int(36 * z)))
            d = ImageDraw.Draw(self.slip_card, "RGBA")
            d.line((36 * z, 84 * z, w - 36 * z, 84 * z), fill=(255, 255, 255, 40), width=max(1, int(2 * z)))
            self.row_spr = []
            for r in self.slip_rows:
                col = r.get("color", "text")
                a = txt(str(r.get("text", "")).upper(), 22 * z, "medium", "dim" if col == "text" else col, "mono", 0.06)
                b = G.text_sprite(str(r.get("value", "")), int(34 * z), "bold", col, family="head")
                self.row_spr.append((a, b))

    # ------------------------------------------------------------------ geometry
    def value(self, c, t):
        v = self.v0[c]
        for t0, a, b in self.moves[c]:
            if t >= t0:
                v = M.lerp(a, b, M.ease_in_out(M.prog(t, t0, MOVE)))
        return v

    def panel_xy(self, t):
        z = self.z
        pw, ph = self.panel.width, self.panel.height
        if self.wide:
            k = M.ease_in_out(M.prog(t, 0.0, M.fr(M.F_MORPH))) if self.carry else 1.0
            cx = M.lerp(self.x_from, self.x_to, k) * z
            return cx - pw / 2, 250 * z
        s = min(1.0, self.area.w / pw)
        return self.area.cx - pw * s / 2, self.top + 40 * z

    def knob_xy(self, c, v, px, py):
        z = self.z
        i = CH.index(c)
        cx = px + (PAD_X + STEP * (i + 0.5)) * z
        cy = py + (PAD_TOP + TRACK * (1 - v)) * z
        return cx, cy

    # ------------------------------------------------------------------ draw
    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        d = ImageDraw.Draw(img, "RGBA")
        # расчётный лист
        if self.slip:
            sx, sy = (150 * z, 250 * z) if self.wide else (self.area.x0, self.top + 640 * z)
            k = self.card(img, t, self.slip_card, sx, sy, self.t_slip, 0, vd, "bottom", name="slip", T=T)
            if k > 0:
                xo = self.gone(t, "slip")
                for j, ((a, b), t0) in enumerate(zip(self.row_spr, self.t_rows)):
                    kr = M.appear(t, t0)[0]
                    if kr <= 0:
                        continue
                    al = kr * k * (1 - xo) * vd
                    ry = sy + (120 + 86 * j) * z + M.bob(T, 0.0) * z + (1 - kr) * 12 * z + xo * 12 * z
                    put(img, a, sx + 36 * z, ry + 8 * z, al)
                    put(img, b, sx + self.slip_card.width - 36 * z - b.width, ry, al)
        # пульт
        k_in = M.ease_out_expo(M.prog(t, self.t_mix, M.fr(M.F_APPEAR)))
        xo = self.gone(t, "mixer")
        a = k_in * (1 - xo) * vd
        if a <= 0:
            return
        px, py = self.panel_xy(t)
        py += M.bob(T, 0.4) * z + (1 - k_in) * 24 * z + xo * 12 * z
        lens_on = bool(self.lens) and self.l_ch in CH
        if lens_on:
            kl = M.ease_out_expo(M.prog(t, self.t_lens, M.fr(M.F_APPEAR)))
            al = kl * a
            kx, ky = self.knob_xy(self.l_ch, self.value(self.l_ch, t), px, py)
            if self.wide:
                lx, ly = px - 260 * z, 540 * z
            else:
                lx, ly = self.area.cx, py + self.panel.height + (LENS_R + 60) * z
            if al > 0:   # линия от ручки к лупе — под стеклом пульта, чтобы не перечёркивать фейдеры
                kline = M.line_progress(t, self.t_lens, 16)
                ex, ey = M.lerp(kx - KW * z / 2, lx + LENS_R * z, kline), M.lerp(ky, ly, kline)
                d.line((kx - KW * z / 2, ky, ex, ey), fill=C("accent2", int(200 * al)), width=max(1, int(3 * z)))
        put(img, self.panel, px, py, a)
        on = None
        for t0, c in self.focus:
            if t >= t0:
                on = c
        for c in CH:
            v = self.value(c, t)
            cx, cy = self.knob_xy(c, v, px, py)
            lit = c == on or (c == self.hl and (not self.lens or t >= self.t_lens))
            kind = "master" if c == "INCOME" else ("hl" if lit else "trait")
            if c == "INCOME":   # подсветка дорожки мастера ниже ручки
                y1 = py + (PAD_TOP + TRACK) * z
                d.rounded_rectangle((cx - 5 * z, cy, cx + 5 * z, y1), 5 * z, fill=C("accent", int(200 * a)))
            spr = self.knob[kind]
            put(img, spr, cx - spr.width / 2, cy - spr.height / 2, a)
        # лупа
        if lens_on:
            if al > 0:
                put(img, self.lens_spr, lx - self.lens_c, ly - self.lens_c, al, 0.9 + 0.1 * kl)
                # увеличенная дорожка: призрак «до» в центре, ручка «после» выше на shift; низ — под подпись ZOOM
                d.rounded_rectangle((lx - 8 * z, ly - (LENS_R - 18) * z, lx + 8 * z, ly + (LENS_R - 80) * z), 8 * z,
                                    fill=(0, 0, 0, int(160 * al)), outline=(255, 255, 255, int(50 * al)))
                ks = M.ease_out_back(M.prog(t, self.t_shift, MOVE)) if hasattr(M, "ease_out_back") else \
                    M.ease_in_out(M.prog(t, self.t_shift, MOVE))
                sh = float(self.lens.get("shift", 60)) * z * ks
                g, h = self.lens_big["ghost"], self.lens_big["hl"]
                put(img, g, lx - g.width / 2, ly + 20 * z - g.height / 2, al * min(1.0, ks * 2))
                put(img, h, lx - h.width / 2, ly + 20 * z - sh - h.height / 2, al)
                put(img, self.lens_zoom, lx - self.lens_zoom.width / 2, ly + (LENS_R - 52) * z, al)
                ka = M.appear(t, self.t_shift + 0.2)[0]
                if self.wide:
                    put(img, self.lens_txt, lx - self.lens_txt.width / 2, ly - LENS_R * z - 90 * z, al * ka)
                else:
                    put(img, self.lens_txt, lx + LENS_R * z + 24 * z, ly - self.lens_txt.height / 2, al * ka)
