"""Пакет lab: шаблоны crowd (толпа = выборка) и verdict (вердикт отдельной сценой)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from ... import gfx as G
from ... import motion as M
from ...lang import ui
from ..registry import P, template
from .base import LabTemplate
from .elements import C, SS, _down, _focus_list, _ss_canvas, person_icon, put, ring_pad, study_card, txt
from .hero import HERO_H, HeroMixin

@template("crowd", aliases=("lab_crowd",),
          doc="lab · Crowd: толпа из N иконок = реальная выборка, подсветка отдельных людей с ярлыками; "
              "опц. карточка исследования, шкала-диапазон и цифра слева (может морфить цифру прошлой сцены).",
          params={"hero": P({"value": 66, "from_prev": True, "caption": "median days", "sub": "", "color": "accent", "at": "66", "strike_at": "w:took"},
                                 "цифра слева {value, from, from_prev, caption, sub, color, at, strike_at}"),
                  "study": P({"authors": "Lally, van Jaarsveld, Potts & Wardle", "where": "Eur. J. of Social Psychology · 2010 · n = 96", "evidence": 3, "at": "2010"},
                             "карточка исследования {authors, where, evidence 1–3, at}"),
                  "crowd": P({"n": 96, "cols": 16, "at": "96", "highlight": [{"index": 19, "label": "18 days", "color": "accent", "at": "18"}]},
                             "толпа {n, cols, at, highlight[{index, label, color, at}]}"),
                  "range": P({"min": 18, "max": 254, "mark": 66, "min_label": "18 days", "max_label": "~254 days", "mark_label": "66 · median", "at": "66"},
                             "шкала-диапазон {min, max, mark, *_label, at}"),
                  **LabTemplate.COMMON},
          beats="элементы — по `at`; люди толпы появляются волной за ~0,6 с")
class LabCrowd(HeroMixin, LabTemplate):
    def plan_body(self):
        self.hero_plan()
        st, cr, rg = self.p.get("study"), self.p.get("crowd"), self.p.get("range")
        self.s_t = self.at(st.get("at"), 0.3) if st else None
        self.cr_t = self.at(cr.get("at"), (self.s_t or 0.3) + 0.3) if cr else None
        self.hl = []
        if cr:
            for i, h in enumerate(cr.get("highlight") or []):
                self.hl.append((h, self.at(h.get("at"), self.cr_t + 1.5 + 0.4 * i)))
        self.r_t = self.at(rg.get("at"), self.D * 0.6) if rg else None
        order = [x for x in (self.s_t, self.r_t, self.h_t if self.hero else None) if x is not None]
        self.fl = _focus_list(sorted(order), self.v_t or self.exit_t)

    def sfx_body(self):
        ev = self.hero_sfx() if self.hero else []
        ev += [(x, "pop") for x in (self.s_t, self.cr_t, self.r_t) if x is not None]
        ev += [(t0, "tick") for _, t0 in self.hl]
        return ev

    def setup_body(self):
        z = self.z
        st = self.p.get("study")
        colw = 724 if self.wide else int(self.area.w / z)  # ширина колонки справа; в высоком кадре — вся рамка
        self.study = study_card(st.get("authors", ""), st.get("where", ""), int(st.get("evidence", 3)), z, colw,
                                (ui(self.ctx.get("language"), "study"), ui(self.ctx.get("language"), "evidence"))) if st else None
        self.study_ring = ring_pad(self.study.width, self.study.height, int(18 * z)) if st else None
        cr = self.p.get("crowd")
        if cr:
            n = int(cr.get("n", 96))
            self.scale_note = None
            if n > 400:
                self.scale_note = txt(f"1 icon = {int(math.ceil(n / 400))} people", 18 * z, "medium", "dim", "mono")
                n = int(math.ceil(n / math.ceil(n / 400)))
            cols = int(cr.get("cols", 16 if n <= 128 else 24))
            rows = int(math.ceil(n / cols))
            area_w = colw * z
            area_h = (300 if not self.p.get("range") else 300) * z
            cw = area_w / cols
            ch = min(50 * z, area_h / rows)
            pw = min(30 * z, cw * 0.66)
            self.pw, self.ph = int(pw), int(pw * 1.2)
            self.cells = [((i % cols) * cw, (i // cols) * ch, (i % cols) * 0.045 + (i // cols) * 0.03) for i in range(n)]
            self.p_white = person_icon(self.pw, self.ph, "text")
            self.p_col = {c: person_icon(self.pw, self.ph, c) for c in ("accent", "accent2", "true", "myth", "half")}
            self.tags = []
            for h, t0 in self.hl:
                c = h.get("color", "accent")
                lab = txt(h.get("label", ""), 18 * z, "medium", "bg", "mono")
                w, hh = int(lab.width + 20 * z), int(lab.height + 8 * z)
                im, d = _ss_canvas(w, hh)
                d.rounded_rectangle((0, 0, w * SS - 1, hh * SS - 1), 8 * z * SS, fill=C(c))
                tg = _down(im, w, hh)
                tg.alpha_composite(lab, (int(10 * z), int(4 * z)))
                self.tags.append(tg)
        rg = self.p.get("range")
        if rg:
            self.rl = txt(rg.get("min_label", str(rg.get("min"))), 19 * z, "medium", "dim", "mono")
            self.rr = txt(rg.get("max_label", str(rg.get("max"))), 19 * z, "medium", "dim", "mono")
            self.rm = txt(rg.get("mark_label", str(rg.get("mark"))), 19 * z, "medium", "accent", "mono")
            w = int(colw * z)
            grad = np.zeros((max(2, int(4 * z)), w, 4), np.uint8)
            c1, c2 = np.array(self.style.pal["accent"]), np.array(self.style.pal["accent2"])
            for x in range(w):
                grad[:, x, :3] = c1 + (c2 - c1) * x / max(1, w - 1)
            grad[:, :, 3] = 255
            self.track = Image.fromarray(grad, "RGBA")

    def _layout(self):
        """Левый верх карточки исследования, толпы и шкалы. 16:9 — колонка справа (x = 1100); высокий кадр —
        стопка: исследование в слоте над цифрой, толпа и шкала под ней."""
        z = self.z
        if self.wide:
            return (1100 * z, 184 * z), (1100 * z, 420 * z), (1100 * z, 752 * z)
        x = self.area.x0
        y = (self.hero_xy(self.hero)[1] + HERO_H * z) if self.hero else self.top + (
            self.study.height + 50 * z if self.study is not None else 0)
        cr_h = (self.cells[-1][1] + self.ph) if self.p.get("crowd") and self.cells else 0
        return (x, self.top), (x, y + 30 * z), (x, y + 30 * z + cr_h + 50 * z)

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {a: M.focus(t, a, b) for a, b in self.fl}
        (sx, sy), (x0c, y0c), (x0r, y0r) = self._layout()
        if self.hero:
            self.draw_hero(img, t, T, vd * (M.lerp(1, 0.55 / 0.32, M.ease_in_out(M.prog(t, (self.v_t or 1e9) - 0.15, 0.35))) if self.v_t else 1),
                           foc.get(self.h_t, (1, 0))[1] if self.fl else 1)
        if self.study is not None:
            br, act = foc.get(self.s_t, (1, 0))
            self.card(img, t, self.study, sx, sy, self.s_t, act, br * vd, "right", name="study", ph=1.7, T=T, ring=self.study_ring)
        if self.p.get("crowd"):
            x0, y0 = x0c, y0c
            xo = self.gone(t, "crowd")
            for i, (cx, cy, dl) in enumerate(self.cells):
                k = M.ease_out_expo(M.prog(t, self.cr_t + dl, 0.3))
                if k <= 0:
                    continue
                spr, s, a = self.p_white, 1.0, k * 0.72
                for j, (h, t0) in enumerate(self.hl):
                    if h.get("index") == i:
                        hk = M.ease_out_expo(M.prog(t, t0, 0.35))
                        if hk > 0:
                            spr, s, a = self.p_col.get(h.get("color", "accent"), self.p_white), M.lerp(1, 1.35, hk), M.lerp(a, 1, hk)
                put(img, spr, x0 + cx, y0 + cy + (1 - k) * 12 * z, a * vd * (1 - xo), s)
            for j, (h, t0) in enumerate(self.hl):
                i = h.get("index", 0)
                if i >= len(self.cells):
                    continue
                cx, cy, _ = self.cells[i]
                k = M.spring(M.prog(t, t0, 0.5))
                tg = self.tags[j]
                put(img, tg, x0 + cx + self.pw / 2, y0 + cy - 34 * z + tg.height / 2 * 0, min(1, k * 1.4) * vd * (1 - xo),
                    M.lerp(0.6, 1, k), anchor="c")
            if self.scale_note is not None:
                put(img, self.scale_note, x0, y0 - 30 * z, M.appear(t, self.cr_t)[0] * vd)
        rg = self.p.get("range")
        if rg:
            br, act = foc.get(self.r_t, (1, 0))
            k = M.ease_in_out(M.prog(t, self.r_t, 0.55))
            if k > 0:
                xo = self.gone(t, "range")
                a = M.lerp(0.7, 1, act) * vd * (1 - xo)
                x0, y0 = x0r, y0r
                tw = int(self.track.width * k)
                if tw > 1:
                    put(img, self.track.crop((0, 0, tw, self.track.height)), x0, y0 + 30 * z, a)
                put(img, self.rl, x0, y0 + 48 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.05, 0.3)) * a)
                put(img, self.rr, x0 + self.track.width - self.rr.width, y0 + 48 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.4, 0.3)) * a)
                lo, hi, mk = float(rg.get("min", 0)), float(rg.get("max", 1)), float(rg.get("mark", 0))
                mx = x0 + self.track.width * (mk - lo) / max(1e-6, hi - lo)
                sk = M.spring(M.prog(t, self.r_t + 0.35, 0.5))
                if sk > 0:
                    d = ImageDraw.Draw(img, "RGBA")
                    r = 18 * z * M.lerp(0.3, 1, sk)
                    cy = y0 + 32 * z
                    ring = G.glowify(G.rrect((int(2 * r) + 1, int(2 * r) + 1), int(r), C("bg"), C("accent"), max(2, int(4 * z))), "accent", 12 * z, 0.6)
                    put(img, ring, mx, cy, min(1, sk * 1.5) * a, anchor="c")
                    put(img, self.rm, mx - self.rm.width / 2, y0 - 30 * z, M.ease_out_expo(M.prog(t, self.r_t + 0.5, 0.3)) * a)


@template("verdict", aliases=("lab_verdict",),
          doc="lab · Вердикт отдельной сценой: штамп TRUE/HALF-TRUE/MYTH/NO EVIDENCE падает пружиной, вспышка цвета "
              "вердикта, подпись; перенесённая цифра (keep: [hero]) видна приглушённой. Разрыв ритма.",
          params={"verdict": P({"verdict": "MYTH", "sub": "21 days → median *66*", "at": "w:verdict"},
                               "штамп {verdict: TRUE|HALF-TRUE|MYTH|NO EVIDENCE, sub, at}"),
                  **{k: LabTemplate.COMMON[k] for k in ("neuron", "chrome", "keep", "source")}},
          beats="штамп — по verdict.at (по умолчанию 0,3 с)")
class LabVerdict(HeroMixin, LabTemplate):
    def plan_body(self):
        if not self.p.get("verdict"):
            self.p = dict(self.p, verdict={"verdict": "MYTH"})
            self.v_t = 0.3
        self.carry = self.state.get("lab_hero")

    def draw_body(self, img, t, T):
        if self.carry:
            z = self.z
            n = self._num(self.carry["value"], self.carry.get("color", "text"), z)
            x, y = (self.carry.get("x", 120) * z, (self.carry.get("y", 470) + 34) * z) if self.wide else self.hero_xy(self.carry)
            self._draw_num(img, n, x, y + M.bob(T, 2) * z, 0.55)
