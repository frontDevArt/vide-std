"""Пакет kit: kinetic — кинетическая типографика для коротких роликов (Reels, TikTok): слова фразы влетают крупно
под речь, акцентные — ударом и плашкой цвета акцента; страница не влезла — уезжает вверх, следующая влетает.

Текст в кадре и есть речь, поэтому субтитры у такой сцены не рисуются (`speech_on_screen`), в .srt они остаются.
"""
from __future__ import annotations

import re

from ... import gfx as G
from ...gfx import blitc, eo, eob, lerp, prog
from ..lab.triggers import _norm
from ..registry import P, template
from .base import KitTemplate

POP = 0.24      # с: слово влетает
LEAD = 0.06     # с: начало чуть раньше звука — так воспринимается синхроннее
PAGE_OUT = 0.2  # с: страница уезжает перед первым словом следующей


def tokens(text):
    """'Вас *ищут* в *самом центре*.' → [('Вас', False), ('ищут', True), ('в', False), ('самом', True),
    ('центре.', True)]. Звёздочки — акцент (можно на несколько слов), пунктуация снаружи остаётся в слове."""
    out, on = [], False
    for raw in str(text or "").split():
        start = re.match(r"[^\w*]*\*", raw) is not None
        end = re.search(r"\*\W*$", raw) is not None
        w = raw.replace("*", "")
        if w:
            out.append((w, on or start))
        on = (on or start) and not end
    return out


def glue(toks, times):
    """Знак без букв ('—', '…') — к предыдущему слову: одинокое тире в начале строки выглядит обрывом."""
    out, tt = [], []
    for (w, hl), t in zip(toks, times):
        if out and not re.search(r"\w", w):
            out[-1] = (out[-1][0] + " " + w, out[-1][1])
            continue
        out.append((w, hl))
        tt.append(t)
    return out, tt


def word_times(n, words, D, start=0.2):
    """Моменты n слов в кадре: по словам озвучки, если их столько же; иначе — пропорционально внутри речи;
    без голоса — равномерно от start до 2/3 сцены."""
    if words and len(words) == n:
        return [w["t0"] for w in words]
    if words:
        a, b = words[0]["t0"], words[-1]["t0"]
    else:
        a, b = start, max(start + 0.3, D * 0.66)
    return [lerp(a, b, i / (n - 1)) if n > 1 else a for i in range(n)]


@template("kinetic", aliases=("kinetic",),
          doc="Кинетический текст для Reels и TikTok: слова фразы влетают крупно под речь (пружина), *акцент* — "
              "ударом и плашкой цвета акцента; не влезло в lines_max строк — страница уезжает вверх, следующая "
              "влетает. Текст в кадре — сама речь, поэтому субтитров у сцены нет (в .srt остаются).",
          params={"text": P(None, "текст в кадре, *слово* — акцент; по умолчанию — слова озвучки сцены", str),
                  "accent": P([], "без text: слова озвучки с акцентом ['ищут', 'вас']", list),
                  "size": P(100, "кегль, дизайн-пиксели 1080"),
                  "lines_max": P(3, "строк на страницу"),
                  "marker": P(True, "акцент на плашке цвета акцента (иначе — цветом)"),
                  "zoom": P(0.05, "медленный наезд на текст за сцену, доля"),
                  "color": KitTemplate.COMMON["color"]},
          beats="каждое слово — со своим словом озвучки (text по числу слов совпадает с речью) или равномерно по речи")
class Kinetic(KitTemplate):
    speech_on_screen = True  # render.frame не рисует субтитры поверх

    def setup(self):
        text = self.p.get("text")
        if text:
            toks = tokens(text)
        else:
            acc = {_norm(a) for a in self.p.get("accent") or []}
            toks = [(w["w"], _norm(w["w"]) in acc) for w in self.words]
        toks, times = glue(toks, word_times(len(toks), self.words, self.D))
        self.n = len(toks)
        if not self.n:
            self.items, self.pages = [], []
            return
        size = self.fs(float(self.p.get("size", 100)))
        f = G.font(size, "black", "head", style=self.style)
        sp = f.getlength(" ")
        marker = bool(self.p.get("marker", True))
        ink = "bg_bot" if marker else self.c
        sprites = []
        for w, hl in toks:
            spr = G.text_sprite(w, size, "black", ink if hl else "text", family="head", style=self.style)
            if hl and marker:  # плашка под словом: текст цветом фона на акценте — читается на любой палитре
                pad = int(size * 0.12)
                pl = G.rrect((spr.width + 2 * pad, spr.height), int(size * 0.16), self.style.col(self.c))
                pl.alpha_composite(spr, (pad, 0))
                spr = pl
            sprites.append(spr)
        box = self.safe  # субтитров у сцены нет — вся зона площадки, а не area над их полосой
        maxw = box.w * 0.92
        lines, cur, cw = [], [], 0.0
        for i, s in enumerate(sprites):
            w = s.width
            if cur and cw + sp + w > maxw:
                lines.append(cur)
                cur, cw = [], 0.0
            cw += (sp if cur else 0) + w
            cur.append(i)
        lines.append(cur)
        lm = max(1, int(self.p.get("lines_max", 3)))
        lh = size * 1.18
        self.items, self.pages = [None] * self.n, []
        for p0 in range(0, len(lines), lm):
            pl = lines[p0:p0 + lm]
            top = box.cy - lh * len(pl) / 2 + lh / 2
            for li, L in enumerate(pl):
                ws = [sprites[i].width for i in L]
                x = box.cx - (sum(ws) + sp * (len(L) - 1)) / 2
                for i, w in zip(L, ws):
                    self.items[i] = {"spr": sprites[i], "x": x + w / 2, "y": top + li * lh, "t": times[i] - LEAD,
                                     "hl": toks[i][1], "page": len(self.pages)}
                    x += w + sp
            self.pages.append(min(times[i] - LEAD for L in pl for i in L))

    def draw(self, img, t, T):
        if not self.n:
            return
        out = self.fade(t)
        z = 1 + float(self.p.get("zoom", 0.05)) * prog(t, 0, self.D)
        cx, cy = self.safe.cx, self.safe.cy
        for it in self.items:
            k = prog(t, it["t"], it["t"] + POP)
            if k <= 0:
                continue
            nxt = self.pages[it["page"] + 1] if it["page"] + 1 < len(self.pages) else None
            gone = prog(t, nxt - PAGE_OUT, nxt) if nxt is not None else 0.0
            if gone >= 1:
                continue
            sc = lerp(0.55, 1.0, eob(k))
            if it["hl"]:  # удар: после влёта ещё раз раздувается и садится
                sc *= 1 + 0.16 * (1 - eo(prog(t, it["t"] + POP * 0.6, it["t"] + POP + 0.3))) * (k >= 1)
            dy = (1 - eo(k)) * 46 * self.u - eo(gone) * 90 * self.u
            a = eo(prog(t, it["t"], it["t"] + POP * 0.5)) * (1 - gone) * out
            blitc(img, it["spr"], cx + (it["x"] - cx) * z, cy + (it["y"] - cy) * z + dy, a, sc * z)
