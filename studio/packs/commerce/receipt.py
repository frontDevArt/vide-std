"""Пакет commerce: чек из принтера сбоку кадра — миксин для шаблонов lab (`Receipt`).

Строки печатаются по словам-триггерам (новая — сверху, у щели), чек переживает склейку через state (`RC_STATE`:
строки и видимость) и может оторваться (`tear_at`) и крупно выехать в `tear_to`.
"""
from __future__ import annotations

import functools
import math

from PIL import Image, ImageDraw

from ... import gfx as G
from ... import motion as M
from ..lab.elements import C, put
from .elements import receipt_paper

RECEIPT_DEFAULTS = {"title": "RECEIPT", "lines": [{"text": "ITEM|$1", "at": None}], "tear_at": None,
                    "tear_to": {"x": 960, "y": 560, "scale": 1.7, "rot": -4}}


class Receipt:
    """Миксин к LabTemplate: параметр `receipt` ({title, lines: [{text: "СЛЕВА|СПРАВА", at}], at, tear_at, tear_to});
    строка без «|» — итог по центру. Шаблон зовёт receipt_plan / receipt_sfx / draw_receipt, в state_out — receipt_state."""
    RC_STATE = "receipt"
    RC_TITLE = "RECEIPT"
    RC_W, RC_LH, RC_X, RC_SLOT = 340, 40, 1824, 176

    def receipt_plan(self):
        r = self.p.get("receipt")
        self.rc = r
        self.rc_title = str((r or {}).get("title") or self.RC_TITLE)
        st = self.state.get(self.RC_STATE) or {}
        self.rc_prev = list(st.get("lines") or [])
        self.rc_was = bool(st.get("visible"))
        new = (r or {}).get("lines") or []
        self.rc_t = self.seq_times(new, 0.6) if r else []
        self.rc_new = [str(x.get("text", "")) for x in new] if r else []
        self.rc_all = self.rc_prev + self.rc_new
        self.rc_in = 0.0 if self.rc_was else self.at((r or {}).get("at"), 0.3)
        self.t_tear = self.at((r or {}).get("tear_at"), None) if r else None

    def receipt_state(self):
        return {"lines": self.rc_all, "visible": bool(self.rc) and "receipt" in self.keep}

    def receipt_sfx(self):
        ev = [(x, "tick") for x in self.rc_t]
        if self.t_tear is not None:
            ev += [(self.t_tear, "swish"), (self.t_tear + 0.8, "pop")]
        return ev

    @functools.lru_cache(maxsize=32)
    def _paper(self, lines, hl, torn=False, zz=None):
        """Бумага чека (elements.receipt_paper); zz — масштаб отрисовки (оторванный чек крупнее — рисуем сразу в его
        размере, без апскейла)."""
        return receipt_paper(lines, hl, torn, zz or self.z, self.rc_title, self.RC_W, self.RC_LH)

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
