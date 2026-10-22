"""Пакет core: общие текстовые шаблоны — title, statement, bullets, counter, outro."""
from __future__ import annotations

import math

from ... import gfx as G
from ...gfx import blit, blitc, col, eio, eo, eob, lerp, prog
from ..base import Template
from ..registry import P, template


# ============================================================== generic templates
@template("title", aliases=("title",),
          doc="Заставка/глава: маленький надзаголовок + крупный заголовок, неоновая линия.",
          params={"kicker": P("Глава 1", "надзаголовок"), "title": P("Заголовок с *акцентом*", "заголовок, *слово* — акцент")},
          beats="заголовок появляется с первым битом (или сразу)")
class Title(Template):
    def setup(self):
        self.kk = G.text_sprite(self.p.get("kicker", ""), int(48 * self.u * self.k), "semibold", "accent2")
        self.t = G.text_sprite(self.p.get("title", ""), int(110 * self.u * self.k), "black", "text", glow=int(24 * self.u),
                               glow_color="violet", maxw=int(self.W * 0.84))
        self.t0 = max(0.0, self.bt(0, 0.3) - 0.25)

    def draw(self, img, t, T):
        a = self.io(t, 0.01, 0.4, enter=False)
        k1, k2 = prog(t, self.t0, self.t0 + 0.5), prog(t, self.t0 + 0.15, self.t0 + 0.8)
        cy = self.cy
        blitc(img, self.kk, self.W / 2, cy - self.t.height / 2 - 30 * self.u, eo(k1) * a)
        blitc(img, self.t, self.W / 2, cy + (1 - eo(k2)) * 50 * self.u, eo(k2) * a, lerp(0.95, 1, eo(k2)))
        lw = int(self.W * 0.4 * eio(prog(t, self.t0 + 0.4, self.t0 + 1.2)))
        if lw > 4:
            ln = G.glowify(G.rrect((lw, int(6 * self.u)), 3, col("accent")), "accent", 10 * self.u)
            blitc(img, ln, self.W / 2, cy + self.t.height / 2 + 20 * self.u, a)


@template("statement", aliases=("statement",),
          doc="Крупная фраза по центру (*слово* — акцент), опционально иконка сверху и подпись.",
          params={"text": P("Главная *мысль*", "фраза, *слово* — акцент"), "icon": P(None, "иконка сверху (gfx.icon)", str),
                  "color": P("accent", "цвет акцента"), "sub": P(None, "подпись под фразой", str),
                  "at_beat": P(0, "бит появления", int)},
          beats="фраза появляется на бите at_beat, подпись — на следующем")
class Statement(Template):
    def setup(self):
        c = self.p.get("color", "accent")
        self.txt = G.text_sprite(self.p.get("text", ""), int(92 * self.u * self.k), "black", "text", accent=c,
                                 glow=int(20 * self.u), glow_color=c, maxw=int(self.W * 0.84))
        self.ic = G.icon(self.p["icon"], int(200 * self.u), c) if self.p.get("icon") else None
        self.sub = G.text_sprite(self.p["sub"], int(46 * self.u * self.k), "medium", "dim", maxw=int(self.W * 0.8)) if self.p.get("sub") else None
        ab = int(self.p.get("at_beat", 0))
        self.t0 = max(0.0, self.bt(ab, 0.3) - 0.2)
        self.t1 = self.bt(ab + 1, self.t0 + 1.2) - 0.1

    def draw(self, img, t, T):
        a = self.io(t, 0.01, 0.4, enter=False)
        cy = self.cy + (40 * self.u if self.ic is not None and not self.vert else 0)
        k = prog(t, self.t0, self.t0 + 0.55)
        if self.ic is not None:
            blitc(img, self.ic, self.W / 2, cy - self.txt.height / 2 - self.ic.height * 0.42, eo(k) * a, lerp(0.6, 1, eob(k)))
        blitc(img, self.txt, self.W / 2, cy + (1 - eo(k)) * 40 * self.u, eo(k) * a)
        if self.sub is not None:
            k2 = prog(t, self.t1, self.t1 + 0.5)
            blitc(img, self.sub, self.W / 2, cy + self.txt.height / 2 + 60 * self.u, eo(k2) * a)


@template("bullets", aliases=("bullets",),
          doc="Заголовок + список пунктов с иконками; пункт i появляется на бите first_beat+i.",
          params={"header": P("Три шага", "заголовок"), "items": P([{"icon": "check", "text": "Пункт"}], "пункты {icon, text, color}"),
                  "first_beat": P(1, "бит первого пункта", int)},
          beats="заголовок — с первым битом, пункты — по битам")
class Bullets(Template):
    def setup(self):
        self.h = G.text_sprite(self.p.get("header", ""), int(76 * self.u * self.k), "black", "text", glow=int(16 * self.u),
                               glow_color="violet", maxw=int(self.W * 0.84))
        colors = ["cyan", "magenta", "lime", "amber", "violet"]
        self.items = []
        fb = int(self.p.get("first_beat", 1))
        its = self.p.get("items") or []
        for i, it in enumerate(its):
            c = it.get("color", colors[i % 5])
            ic = G.icon(it.get("icon", "check"), int(84 * self.u * self.k), c)
            tx = G.text_sprite(it.get("text", ""), int(52 * self.u * self.k), "bold", "text", align="left",
                               maxw=int(self.W * (0.64 if self.vert else 0.5)))
            t0 = self.bt(fb + i, lerp(0.8, self.D - 0.8, i / max(1, len(its))))
            self.items.append((ic, tx, max(0.1, t0 - 0.1)))

    def draw(self, img, t, T):
        a = self.io(t, 0.3, 0.4)
        n = len(self.items)
        step = 150 * self.u * self.k
        block = self.h.height + 40 * self.u + step * n
        top = self.cy - block / 2 + self.h.height / 2
        blitc(img, self.h, self.W / 2, top, a)
        y0 = top + self.h.height / 2 + 40 * self.u + step / 2
        bw = max([ic.width + 10 * self.u + tx.width for ic, tx, _ in self.items] or [0])
        x0 = (self.W - bw) / 2 if not self.vert else self.W * 0.12
        for i, (ic, tx, t0) in enumerate(self.items):
            k = prog(t, t0, t0 + 0.45)
            if k <= 0:
                continue
            y = y0 + i * step
            dx = (1 - eo(k)) * 80 * self.u
            blitc(img, ic, x0 + ic.width / 2 + dx, y, eo(k) * a)
            blit(img, tx, x0 + ic.width + 10 * self.u + dx, y - tx.height / 2, eo(k) * a)


@template("counter", aliases=("counter",),
          doc="Большое число, которое «набегает» от from до to во время бита, с подписью.",
          params={"from": P(0, "начальное значение"), "to": P(100, "конечное значение"), "suffix": P("", "после числа (%)"),
                  "label": P("подпись", "подпись под числом"), "at_beat": P(0, "бит, во время которого идёт счёт", int),
                  "color": P("amber", "цвет числа")},
          beats="счёт идёт в течение бита at_beat")
class Counter(Template):
    def setup(self):
        ab = int(self.p.get("at_beat", 0))
        self.t0, self.t1 = self.bt(ab, 0.3), self.be(ab, self.D * 0.7)
        self.lbl = G.text_sprite(self.p.get("label", ""), int(50 * self.u * self.k), "semibold", "dim", maxw=int(self.W * 0.8))

    def draw(self, img, t, T):
        a = self.io(t, 0.3, 0.4)
        k = eio(prog(t, self.t0, self.t1))
        v = lerp(float(self.p.get("from", 0)), float(self.p.get("to", 100)), k)
        s = f"{int(round(v))}{self.p.get('suffix', '')}"
        c = self.p.get("color", "amber")
        num = G.text_sprite(s, int(220 * self.u), "black", c, glow=int(30 * self.u), glow_color=c)
        cy = self.cy - 30 * self.u
        blitc(img, num, self.W / 2, cy, a, 1 + 0.03 * math.sin(k * math.pi))
        blitc(img, self.lbl, self.W / 2, cy + num.height / 2 + 30 * self.u, a)


@template("outro", aliases=("outro",),
          doc="Финальный текст с подписью; держится до конца ролика.",
          params={"text": P("Твоё *время* — твой выбор", "финальный текст, *слово* — акцент"), "sub": P("", "подпись")},
          beats="текст появляется сразу или с первым битом")
class Outro(Template):
    def setup(self):
        self.txt = G.text_sprite(self.p.get("text", ""), int(96 * self.u), "black", "text", accent="cyan",
                                 glow=int(26 * self.u), glow_color="violet", maxw=int(self.W * 0.82))
        self.sub = G.text_sprite(self.p["sub"], int(40 * self.u), "medium", "dim") if self.p.get("sub") else None
        self.t0 = max(0.0, self.bt(0, 0.2) - 0.2)

    def draw(self, img, t, T):
        k = prog(t, self.t0, self.t0 + 0.7)
        a = eo(k) * (1 if self.last else 1 - prog(t, self.D - 0.4, self.D))
        y = self.cy
        blitc(img, self.txt, self.W / 2, y + (1 - eo(k)) * 40 * self.u, a)
        if self.sub is not None:
            blitc(img, self.sub, self.W / 2, y + self.txt.height / 2 + 50 * self.u, eo(prog(t, self.t0 + 0.5, self.t0 + 1.1)) * a)
