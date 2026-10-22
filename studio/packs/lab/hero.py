"""Пакет lab: огромная цифра (HeroMixin — счётчик, «миф → реальность») и шаблон hero_stack."""
from __future__ import annotations

import functools

from PIL import Image, ImageDraw

from ... import gfx as G
from ... import motion as M
from ..registry import P, template
from .base import LabTemplate
from .elements import C, SS, _down, _focus_list, _ss_canvas, glass, put, rich, ring_pad, tile, txt


# ===================================================================== hero number (shared)
class HeroMixin:
    """Огромная цифра (Unbounded 300 px) + подпись; счётчик; «Миф → Реальность» с зачёркиванием цветом MYTH.
    hero: {value, from, caption, sub, color: text|accent, at, from_prev, strike_at}."""

    def hero_plan(self):
        h = self.p.get("hero")
        self.hero = h
        if not h:
            return
        self.prev_hero = self.state.get("lab_hero") if h.get("from_prev") else None
        self.h_t = self.at(h.get("at"), 0.4)
        if self.prev_hero:
            self.h_strike = self.at(h.get("strike_at"), self.h_t - 0.45)
            self.h_from = float(h.get("from", self.prev_hero.get("value", 0)))
        else:
            self.h_strike = None
            self.h_from = float(h.get("from", 0))

    def hero_out(self):
        h = self.p.get("hero")
        if not h:
            return None
        return {"value": h.get("value"), "caption": h.get("caption", ""), "sub": h.get("sub", ""),
                "color": h.get("color", "text"), "x": h.get("x", 120), "y": h.get("y", 470)}

    def hero_sfx(self):
        if not self.hero:
            return []
        ev = [(self.h_t, "pop")] + self.ticks(self.h_t + 0.05, 0.9)
        if self.h_strike is not None:
            ev.append((self.h_strike, "swish"))
        return ev

    def _num(self, v, color, z):
        s = f"{int(round(v))}" if isinstance(v, (int, float)) else str(v)
        return num_sprite(s, color, z, 300)

    def _cap(self, cap, sub, z):
        a = txt(str(cap).upper(), 34 * z, "extrabold", "text", "head", 0.08) if cap else None
        b = txt(sub, 20 * z, "medium", "dim", "mono", 0.02) if sub else None
        return a, b

    def _draw_num(self, img, n, x, y, alpha, scale=1.0, blur=0.0):
        """Положить цифру так, чтобы ЧЕРНИЛА начинались в (x, y); масштаб — от левого верхнего угла (как в демо)."""
        spr, off, iw, ih = n
        cx = x + (iw / 2) * scale
        cy = y + (ih / 2) * scale
        put(img, spr, cx, cy, alpha, scale, blur, anchor="c")

    def _strike(self, img, x, y, n, scale, k, alpha):
        """Зачёркивание цветом MYTH: от левого края цифры на 110 % её ширины, по середине высоты."""
        z = self.z
        _, _, iw, ih = n
        bw = int((iw * 1.1 + 28 * z) * scale * k)
        if bw > 2:
            bar = strike_bar(bw, max(2, int(14 * z * scale)), z)
            pad = (bar.height - max(2, int(14 * z * scale))) / 2
            put(img, bar, x - 14 * z * scale - pad, y + ih * 0.5 * scale - bar.height / 2, alpha)

    def draw_hero(self, img, t, T, dim=1.0, focus=1.0):
        h = self.hero
        if not h:
            return
        z = self.z
        # (x, y) из params — верх блока как в демо (top: 470); чернила цифры начинаются на 34 px ниже
        x, y = h.get("x", 120) * z, h.get("y", 470) * z + 34 * z
        if self.prev_hero:
            ph = self.prev_hero
            m = M.ease_in_out(M.prog(t, self.h_t - 0.1, 0.55))
            n = self._num(ph["value"], ph.get("color", "text"), z)
            a = M.lerp(1, 0.55, m) * dim
            sc = M.lerp(1, 0.32, m)
            px, py = x + M.lerp(0, 520, m) * z, y + M.lerp(0, 10, m) * z + M.bob(T, 2) * z
            self._draw_num(img, n, px, py, a, sc)
            ca, cb = self._cap(ph.get("caption"), ph.get("sub"), z)
            cy = y + n[3] + 42 * z
            put(img, ca, x, cy, (1 - m) * dim)
            put(img, cb, x, cy + 46 * z, (1 - m) * dim)
            sk = M.ease_in_out(M.prog(t, self.h_strike, M.fr(M.F_FOCUS)))
            if sk > 0:
                self._strike(img, px, py, n, sc, sk, a)
        k = M.ease_out_expo(M.prog(t, self.h_t, M.fr(M.F_APPEAR)))
        if k <= 0:
            return
        v = M.count(t, self.h_t, self.h_from, float(h.get("value", 0))) \
            if isinstance(h.get("value"), (int, float)) else h.get("value")
        n = self._num(v, h.get("color", "text"), z)
        xo = self.gone(t, "hero")
        a = k * (1 - xo) * dim * M.lerp(0.65, 1, focus)
        yy = y + (1 - k) * 24 * z + M.bob(T, 2) * k * z + xo * 12 * z
        self._draw_num(img, n, x, yy, a, 0.96 + 0.04 * k, (1 - k) * 8)
        ca, cb = self._cap(h.get("caption"), h.get("sub"), z)
        cy = yy + n[3] + 42 * z
        put(img, ca, x, cy, a)
        put(img, cb, x, cy + 46 * z, a)
        if h.get("strike_at") is not None and not self.prev_hero:
            sk = M.ease_in_out(M.prog(t, self.at(h["strike_at"], self.D), M.fr(M.F_FOCUS)))
            if sk > 0:
                self._strike(img, x, yy, n, 1.0, sk, a)


@functools.lru_cache(maxsize=256)
def num_sprite(s, color, z, size):
    """Огромная цифра Unbounded 800 со свечением. -> (спрайт, отступ до чернил, ширина и высота чернил)."""
    f = G.font(int(size * z), "extrabold", "num")
    l, t, r, b = f.getbbox(s)
    p = int(8 * z)
    base = Image.new("RGBA", (r - l + 2 * p, b - t + 2 * p), (0, 0, 0, 0))
    ImageDraw.Draw(base).text((p - l, p - t), s, font=f, fill=C(color))
    rad = (60 if color == "accent" else 40) * z
    spr = G.glowify(base, color, rad, 0.45 if color == "accent" else 0.15)
    return spr, (spr.width - base.width) // 2 + p, r - l, b - t


@functools.lru_cache(maxsize=64)
def strike_bar(w, h, z):
    return G.glowify(G.rrect((w, h), h // 2, C("myth")), "myth", 14 * z, 0.6)


# ===================================================================== templates §5


@template("hero_stack", aliases=("lab_hero_stack",), formats=("horizontal",),
          doc="lab · Hero + Stack: слева огромная цифра (счётчик, «миф → реальность»), справа стопка 3–4 карточек, "
              "линии с бегущими точками от цифры к карточкам; опц. карточка утверждения сверху-слева.",
          params={"claim": P({"label": "VIRAL CLAIM", "text": "“It takes *21 days* to build a habit.”", "meta": "", "at": "w:says", "qmark": True},
                             "карточка утверждения сверху-слева {label, text, meta, at, qmark}"),
                  "hero": P({"value": 21, "from": 0, "caption": "days", "sub": "the popular claim", "color": "text", "at": "21"},
                            "цифра слева {value, from, caption, sub, color, at, from_prev, strike_at}"),
                  "cards": P([{"icon": "book", "title": "Title", "sub": "mono subtitle", "chip": None, "chip_color": "noev", "at": "w:book"}],
                             "стопка карточек {icon, title, sub, chip, chip_color, at}"),
                  "lines": P(True, "линии с бегущими точками от цифры к карточкам"), **LabTemplate.COMMON},
          beats="каждый элемент — по своему `at` (слово/бит/секунды); без `at` — стаггер")
class LabHeroStack(HeroMixin, LabTemplate):
    def plan_body(self):
        self.hero_plan()
        c = self.p.get("claim")
        self.c_t = self.at(c.get("at"), 0.4) if c else None
        self.q_t = self.c_t + 0.55 if c and c.get("qmark", True) else None
        self.cards = self.p.get("cards") or []
        self.k_t = self.seq_times(self.cards, (self.h_t if self.hero else 0.6) + 0.8)
        order = [x for x in [self.c_t, self.h_t if self.hero else None] + self.k_t if x is not None]
        self.fl = _focus_list(sorted(order), self.exit_t)

    def sfx_body(self):
        ev = self.hero_sfx() if self.hero else []
        if self.c_t is not None:
            ev.append((self.c_t, "pop"))
        if self.q_t is not None:
            ev.append((self.q_t, "pop"))
        ev += [(x, "pop") for x in self.k_t]
        return ev

    def setup_body(self):
        z = self.z
        c = self.p.get("claim")
        if c:
            w = int((780 + 72) * z)  # как в демо: 780 — ширина текста, плюс поля 36 + 36
            lab = txt(c.get("label", "VIRAL CLAIM"), 20 * z, "medium", "dim", "mono", 0.08)
            body = rich(c.get("text", ""), 46 * z, 780 * z)
            meta = txt(c["meta"], 19 * z, "medium", "dim", "mono") if c.get("meta") else None
            h = int(30 * z + lab.height + 12 * z + body.height + (14 * z + meta.height if meta else 0) + 30 * z)
            card = glass(w, h, int(18 * z)).copy()
            y = int(30 * z)
            card.alpha_composite(lab, (int(36 * z), y)); y += lab.height + int(12 * z)
            card.alpha_composite(body, (int(36 * z), y)); y += body.height + int(14 * z)
            if meta:
                card.alpha_composite(meta, (int(36 * z), y))
            self.claim_spr = card
            self.claim_ring = ring_pad(w, h, int(18 * z))
            q = int(76 * z)
            img, d = _ss_canvas(q, q)
            d.ellipse((SS, SS, q * SS - SS, q * SS - SS), fill=C("bg"), outline=C("noev"), width=int(3 * z * SS))
            qs = _down(img, q, q)
            qm = txt("?", 38 * z, "extrabold", "noev", "num")
            qs.alpha_composite(qm, ((q - qm.width) // 2 + int(2 * z), (q - qm.height) // 2 - int(2 * z)))
            self.qmark = qs
        self.card_spr = []
        for it in self.cards:
            w, h = int(724 * z), int(120 * z)
            card = glass(w, h, int(18 * z)).copy()
            tl = tile(it.get("icon", "book"), int(72 * z))
            card.alpha_composite(tl, (int(26 * z), (h - tl.height) // 2))
            t1 = txt(it.get("title", ""), 32 * z, "extrabold", "text", "head", 0.01)
            t2 = txt(it.get("sub", ""), 19 * z, "medium", "dim", "mono") if it.get("sub") else None
            x = int(26 * z + tl.width + 24 * z)
            th = t1.height + (6 * z + t2.height if t2 else 0)
            y = int((h - th) / 2)
            card.alpha_composite(t1, (x, y))
            if it.get("chip"):
                cc = it.get("chip_color", "noev")
                cp = txt(it["chip"], 17 * z, "medium", cc, "mono")
                cw, chh = int(cp.width + 24 * z), int(cp.height + 6 * z)
                im2, d2 = _ss_canvas(cw, chh)
                d2.rounded_rectangle((0, 0, cw * SS - 1, chh * SS - 1), chh * SS / 2, outline=C(cc), width=int(1.5 * z * SS))
                chip = _down(im2, cw, chh)
                chip.alpha_composite(cp, (int(12 * z), int(3 * z)))
                card.alpha_composite(chip, (x + t1.width + int(10 * z), y + int((t1.height - chh) / 2 + 3 * z)))
            if t2:
                card.alpha_composite(t2, (x, int(y + t1.height + 6 * z)))
            self.card_spr.append((card, ring_pad(w, h, int(18 * z))))

    def _ys(self):
        z = self.z
        n = len(self.cards)
        top = 330 if n <= 3 else 260
        return [(top + i * 148) * z for i in range(n)]

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        foc = {}
        for (a, b) in self.fl:
            foc[a] = M.focus(t, a, b)
        if self.p.get("claim"):
            br, act = foc.get(self.c_t, (1, 0))
            self.card(img, t, self.claim_spr, 96 * z, 184 * z, self.c_t, act, br * vd, name="claim", ph=0.4, T=T, ring=self.claim_ring)
            if self.q_t is not None:
                k = M.spring(M.prog(t, self.q_t, 0.6))
                a = min(1, k * 1.5) * (1 - self.gone(t, "claim")) * br * vd
                put(img, self.qmark, 96 * z + self.claim_spr.width - 26 * z + 38 * z, 184 * z - 26 * z + 38 * z, a,
                    M.lerp(1.6, 1, k), rot=M.lerp(20, 0, k), anchor="c")
        if self.hero:
            br, act = foc.get(self.h_t, (1, 0))
            self.draw_hero(img, t, T, vd, act if self.fl else 1)
        ys = self._ys()
        d = ImageDraw.Draw(img, "RGBA")
        hx, hy = 700 * z, 600 * z
        for i, (it, (spr, ring), y) in enumerate(zip(self.cards, self.card_spr, ys)):
            t0 = self.k_t[i]
            br, act = foc.get(t0, (1, 0))
            if self.p.get("lines", True) and self.hero:
                self._line(img, d, t, (hx, hy), (1100 * z, y + 60 * z), t0 - 0.25, act, self.gone(t, f"card{i}") or self.gone(t, "cards"))
            self.card(img, t, spr, 1100 * z, y, t0, act, br * vd, "right", name="cards", ph=i, T=T, ring=ring)

    def _line(self, img, d, t, p0, p1, start, act, xo):
        """Кривая от источника к цели (ease-in-out, 22 кадра), узел на конце, бегущие точки."""
        z = self.z
        k = M.line_progress(t, start)
        if k <= 0 or xo >= 1:
            return
        (x0, y0), (x1, y1) = p0, p1
        pts = []
        N = 48
        for i in range(N + 1):
            u = i / N
            # cubic: (x0,y0) (x0+200,y0) (x1-180,y1) (x1,y1) — как в демо
            cx0, cy0, cx1, cy1 = x0 + 200 * z, y0, x1 - 180 * z, y1
            bx = (1 - u) ** 3 * x0 + 3 * (1 - u) ** 2 * u * cx0 + 3 * (1 - u) * u * u * cx1 + u ** 3 * x1
            by = (1 - u) ** 3 * y0 + 3 * (1 - u) ** 2 * u * cy0 + 3 * (1 - u) * u * u * cy1 + u ** 3 * y1
            pts.append((bx, by))
        n = max(2, int(N * k) + 1)
        a = (1 - xo) * M.lerp(0.5, 1, act) * self.vdim(t)
        for i in range(n - 1):
            g = 0.15 + 0.75 * i / N
            d.line((pts[i], pts[i + 1]), fill=C("accent", int(255 * g * a)), width=max(1, int(2.5 * z)))
        if k >= 1:
            ex, ey = pts[-1]
            d.ellipse((ex - 7 * z, ey - 7 * z, ex + 7 * z, ey + 7 * z), fill=C("bg"), outline=C("accent", int(255 * a)), width=int(3 * z))
            for u, al in M.running_dot(t, start + M.fr(M.F_LINE)):
                px, py = pts[min(N, int(u * N))]
                d.ellipse((px - 6 * z, py - 6 * z, px + 6 * z, py + 6 * z), fill=C("accent", int(255 * al * a)))
