"""Свои элементы ролика «twelve-myths» (STYLE §14, новые элементы): доска дел и улика.

`lab_docket` — доска суда: сетка из 12 карточек «CASE 01…12» (6×2 в 16:9, 3×4 в высоком кадре). Текущее дело —
в фокусе (рамка accent, остальные приглушены), закрытое дело несёт плашку вердикта своего цвета; плашка падает
пружиной по слову-триггеру (`close.at`). Закрытые дела копятся через state (`tm_docket`) через весь ролик — даже
когда доски нет в кадре; доска на экране без новой раскладки — `keep: [docket]` + у следующей `from_prev: true`.
`lab_exhibit` — улика: картинка-стикер (PNG с прозрачностью, обычно `assets/images/<ключ>.cut.png` от
`python -m studio images`) слева, бирка «EXHIBIT · CASE 03» над ней, подпись-карточка справа. Нет файла — пунктирная
рамка-заглушка (для stills до генерации).
Координаты — дизайн-пиксели 1920×1080, масштаб self.z; высокий кадр — своя раскладка в рамке self.area.
"""
from __future__ import annotations

import functools
import math

from PIL import Image, ImageDraw

from studio import assets as AS
from studio import gfx as G
from studio import motion as M
from studio.lab import C, SS, VERDICTS, LabTemplate, _down, _focus_list, _ss_canvas, glass, put, ring_pad, txt
from studio.lang import verdict_word
from studio.templates import template

STATE = "tm_docket"
GAP = 24


# ===================================================================== sprites
@functools.lru_cache(maxsize=64)
def tile_sprite(n, title, w, h, z):
    """Карточка дела: «CASE 03» моно сверху; заголовок капсом — только у открытого дела (запечатанные — «?»)."""
    card = glass(w, h, int(18 * z)).copy()
    num = txt(f"CASE {n:02d}", 18 * z, "medium", "dim", "mono", 0.08)
    card.alpha_composite(num, (int(20 * z), int(18 * z)))
    if title:
        t = G.text_sprite(title.upper(), int(26 * z), "extrabold", "text", family="head", maxw=int(w - 40 * z), align="left")
        card.alpha_composite(t, (int(20 * z), int(60 * z)))
    return card


@functools.lru_cache(maxsize=8)
def qmark_sprite(z):
    return txt("?", 64 * z, "extrabold", "dim", "num")


@functools.lru_cache(maxsize=32)
def chip_sprite(verdict, word, z):
    """Мини-штамп вердикта на карточке: обводка цвета вердикта, слово капсом."""
    c = VERDICTS.get(verdict.upper(), "myth")
    t = txt(word.upper(), 24 * z, "extrabold", c, "num", 0.04)
    w, h = int(t.width + 36 * z), int(t.height + 20 * z)
    img, d = _ss_canvas(w, h)
    d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 12 * z * SS, fill=(10, 13, 20, 220), outline=C(c), width=int(3 * z * SS))
    box = _down(img, w, h)
    box.alpha_composite(t, (int(18 * z), int((h - t.height) / 2 + z)))
    return G.glowify(box, c, 14 * z, 0.4)


def dashed_box(w, h, z):
    img, d = _ss_canvas(w, h)
    step, ln = 26 * z * SS, 14 * z * SS
    col, lw = (255, 255, 255, 60), int(2 * z * SS)
    for x in range(0, int(w * SS), int(step)):
        d.line((x, SS, min(x + ln, w * SS), SS), fill=col, width=lw)
        d.line((x, h * SS - SS, min(x + ln, w * SS), h * SS - SS), fill=col, width=lw)
    for y in range(0, int(h * SS), int(step)):
        d.line((SS, y, SS, min(y + ln, h * SS)), fill=col, width=lw)
        d.line((w * SS - SS, y, w * SS - SS, min(y + ln, h * SS)), fill=col, width=lw)
    return _down(img, w, h)


# ===================================================================== docket
@template("lab_docket",
          doc="lab · доска дел ролика twelve-myths: 12 карточек CASE 01–12, фокус на текущем деле, плашка вердикта "
              "падает на карточку по `close.at`. Закрытые дела копятся через state (tm_docket).",
          params={"cases": 12, "from_prev": False, "tiles": {"at": None},
                  "focus": {"case": None, "title": "", "at": None},
                  "close": {"case": None, "verdict": "MYTH", "at": None}, **LabTemplate.COMMON},
          beats="раскладка карточек — от `at` стаггером (с from_prev — сразу); фокус и плашка — по словам `at`")
class LabDocket(LabTemplate):
    def plan_body(self):
        p = self.p
        prev = self.state.get(STATE) or {}
        self.n = int(p.get("cases") or prev.get("cases") or 12)
        self.closed = dict(prev.get("closed") or {})
        self.carry = bool(p.get("from_prev")) and bool(prev.get("visible"))
        t0 = self.at((p.get("tiles") or {}).get("at"), 0.2)
        self.t_tiles = [-10.0 if self.carry else t0 + i * M.fr(4) for i in range(self.n)]
        fc = p.get("focus") or {}
        self.f_case = fc.get("case")
        self.f_title = str(fc.get("title") or "")
        self.t_focus = self.at(fc.get("at"), 0.6) if self.f_case else None
        cl = p.get("close") or {}
        self.c_case = cl.get("case")
        self.c_verdict = str(cl.get("verdict", "MYTH")).upper()
        self.t_close = self.at(cl.get("at"), self.D * 0.6) if self.c_case else None

    def state_out(self):
        out = super().state_out()
        closed = dict(self.closed)
        if self.c_case:
            closed[str(self.c_case)] = self.c_verdict
        out[STATE] = {"cases": self.n, "closed": closed, "visible": "docket" in self.keep}
        return out

    def sfx_body(self):
        ev = [] if self.carry else [(self.t_tiles[0], "pop")] if self.t_tiles else []
        if self.t_focus is not None:
            ev.append((self.t_focus, "swish"))
        if self.t_close is not None:
            ev.append((self.t_close, "thud"))
        return ev

    # ---------- geometry
    def grid(self):
        z = self.z
        if self.wide:
            cols, x0, x1, y0, y1 = 6, 96 * z, self.W - 96 * z, 230 * z, 800 * z
        else:
            a = self.area
            cols, x0, x1, y0, y1 = 3, a.x0, a.x1, self.top + 40 * z, a.y1 - 40 * z
        rows = max(1, math.ceil(self.n / cols))
        g = GAP * z
        w = (x1 - x0 - g * (cols - 1)) / cols
        h = min((y1 - y0 - g * (rows - 1)) / rows, w * (0.95 if self.wide else 1.05))
        top = y0 + ((y1 - y0) - (h * rows + g * (rows - 1))) / 2
        return [(x0 + (i % cols) * (w + g), top + (i // cols) * (h + g)) for i in range(self.n)], int(w), int(h)

    def setup_body(self):
        z = self.z
        self.pos, self.tw, self.th = self.grid()
        self.tiles = [tile_sprite(i + 1, self.f_title if self.f_case == i + 1 else "", self.tw, self.th, z)
                      for i in range(self.n)]
        self.ring = ring_pad(self.tw, self.th, int(18 * z))
        self.q = qmark_sprite(z)
        lang = self.ctx.get("language")
        self.chips = {v: chip_sprite(v, verdict_word(lang, v), z) for v in set(self.closed.values()) | {self.c_verdict}}

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        kf = M.ease_in_out(M.prog(t, self.t_focus, M.fr(M.F_FOCUS))) if self.t_focus is not None else 0.0
        for i, ((x, y), spr, t0) in enumerate(zip(self.pos, self.tiles, self.t_tiles)):
            n = i + 1
            me = self.f_case == n
            dim = vd * (1 - kf * 0.42 * (not me))
            k = self.card(img, t, spr, x, y, t0, act=kf if me else 0.0, dim=dim, name="docket", ph=i * 0.7, T=T,
                          ring=self.ring if me else None)
            if k <= 0:
                continue
            xo = self.gone(t, "docket")
            a = k * (1 - xo) * dim
            yb = y + self.th - 20 * z + M.bob(T, i * 0.7) * k * z + xo * 12 * z
            v = self.closed.get(str(n))
            if self.c_case == n and self.t_close is not None and t >= self.t_close - 0.02:
                ks = M.spring(M.prog(t, self.t_close, M.fr(M.F_STAMP) + 0.25))
                chip = self.chips[self.c_verdict]
                put(img, chip, x + 20 * z + chip.width / 2 - 14 * z, yb - chip.height / 2 + 10 * z, min(1.0, ks * 2) * (1 - xo),
                    M.lerp(1.7, 1.0, ks), rot=M.lerp(14, 6, ks), anchor="c")
                f = M.prog(t, self.t_close - 0.05, 0.6)
                put(img, G.radial(int(self.tw * 1.6), VERDICTS.get(self.c_verdict, "myth"), 0.5, 1.4),
                    x + self.tw / 2, y + self.th / 2, math.sin(f * math.pi) * 0.7, anchor="c")
            elif v:
                chip = self.chips[v]
                put(img, chip, x + 20 * z + chip.width / 2 - 14 * z, yb - chip.height / 2 + 10 * z, a, 1.0, rot=6, anchor="c")
            else:
                put(img, self.q, x + 20 * z, yb - self.q.height + 6 * z, a * 0.6)


# ===================================================================== exhibit
@template("lab_exhibit",
          doc="lab · улика ролика twelve-myths: картинка-стикер слева (PNG с прозрачностью), бирка «EXHIBIT · CASE N» "
              "над ней, подписи-карточки справа. Нет файла — пунктирная заглушка.",
          params={"file": "", "case": 1, "tag": {"at": None},
                  "labels": [{"text": "let it out?", "at": None, "color": "accent"}], **LabTemplate.COMMON},
          beats="картинка — от `at`; подписи — по словам `at`")
class LabExhibit(LabTemplate):
    def plan_body(self):
        p = self.p
        self.t_img = self.at((p.get("tag") or {}).get("at"), 0.2)
        self.lbs = p.get("labels") or []
        self.t_lb = self.seq_times(self.lbs, 1.0)
        self.fl = _focus_list(self.t_lb, self.v_t or self.exit_t)

    def sfx_body(self):
        return [(self.t_img, "swish")] + [(x, "pop") for x in self.t_lb]

    def setup_body(self):
        z = self.z
        self.box = int((600 if self.wide else 560) * z)
        f = self.p.get("file")
        src = AS.path(self.ctx.get("roots") or ["."], f) if f else None
        if src is not None and src.is_file():
            im = Image.open(src).convert("RGBA")
            bb = im.getchannel("A").getbbox()
            if bb:
                im = im.crop(bb)
            s = self.box / max(im.width, im.height)
            self.pic = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
        else:
            self.pic = dashed_box(self.box, self.box, z)
        tg = txt(f"EXHIBIT · CASE {int(self.p.get('case') or 1):02d}", 20 * z, "medium", "text", "mono", 0.1)
        w, h = int(tg.width + 40 * z), int(46 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 220), outline=C("accent", 150), width=int(1.5 * z * SS))
        self.tag = _down(img, w, h)
        self.tag.alpha_composite(tg, (int(20 * z), int((h - tg.height) / 2)))
        self.glow = G.radial(int(self.box * 1.5), "accent", 0.22, 1.6)
        self.lb_spr = []
        for lb in self.lbs:
            col = lb.get("color", "accent")
            t = G.text_sprite(str(lb.get("text", "")), int(32 * z), "bold", "text", family="head", maxw=int(560 * z))
            w, h = int(t.width + 56 * z), int(t.height + 32 * z)
            card = glass(w, h, int(14 * z)).copy()
            dd = ImageDraw.Draw(card, "RGBA")
            dd.rounded_rectangle((int(14 * z), int(h / 2 - 6 * z), int(26 * z), int(h / 2 + 6 * z)), int(6 * z), fill=C(col))
            card.alpha_composite(t, (int(40 * z), int(16 * z)))
            self.lb_spr.append((card, ring_pad(w, h, int(14 * z), col)))

    def draw_body(self, img, t, T):
        z = self.z
        vd = self.vdim(t)
        if self.wide:
            cx, cy = 640 * z, 540 * z
        else:
            cx, cy = self.area.cx, self.top + 60 * z + self.box / 2
        k = M.ease_out_expo(M.prog(t, self.t_img, 0.8))
        xo = self.gone(t, "exhibit")
        a = k * (1 - xo) * vd
        if a > 0:
            drift = 1.0 + 0.035 * M.prog(t, self.t_img, max(1.0, self.D))
            yy = cy + M.bob(T, 0.3, 6.0, 5.0) * z + (1 - k) * 30 * z + xo * 14 * z
            put(img, self.glow, cx, yy, a * 0.9, anchor="c")
            put(img, self.pic, cx, yy, a, (0.92 + 0.08 * k) * drift, (1 - k) * 8, rot=math.sin(T * 0.6) * 1.2, anchor="c")
            put(img, self.tag, cx - self.tag.width / 2, cy - self.box / 2 - 70 * z + (1 - k) * 20 * z, a)
        foc = {s: M.focus(t, s, e) for s, e in self.fl}
        for i, ((spr, ring), t0) in enumerate(zip(self.lb_spr, self.t_lb)):
            if self.wide:
                lx, ly = 1110 * z, (330 + 140 * i) * z
            else:
                lx, ly = self.area.x0 + 20 * z, cy + self.box / 2 + 60 * z + 100 * z * i
            br, act = foc.get(t0, (1, 0))
            self.card(img, t, spr, lx, ly, t0, act, br * vd, "right", name="labels", ph=i, T=T, ring=ring)
