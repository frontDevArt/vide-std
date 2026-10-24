"""Пакет kit: quote и testimonial — цитата и отзыв (ROADMAP C4)."""
from __future__ import annotations

from ... import gfx as G
from ...gfx import blit, blitc, eo, eob, lerp, prog
from ..registry import AT, NUM, P, template
from .base import KitTemplate, avatar, initials, star


@template("quote", aliases=("quote",),
          doc="Цитата: крупная кавычка, текст (*слово* — акцент), автор и кто он; опц. фото автора в круге.",
          params={"text": P("Цитата с *акцентом*", "текст цитаты, *слово* — акцент"),
                  "author": P(None, "автор", str), "role": P(None, "кто он (вторая строка)", str),
                  "photo": P(None, "фото автора (assets/…, в assets.yaml)", str),
                  "at": P(0, "появление текста: бит | '1.5s' | слово озвучки", AT),
                  "author_at": P(None, "появление автора (по умолчанию — через 0,8 с после текста)", AT),
                  "color": KitTemplate.COMMON["color"]},
          beats="кавычка и текст — с `at`, автор — с `author_at`")
class Quote(KitTemplate):
    def setup(self):
        a = self.area
        mw = int(a.w * (0.9 if self.vert else 0.78))
        n = len(str(self.p.get("text", "")))
        size = 76 if n < 90 else 62 if n < 160 else 50
        self.txt = G.text_sprite(self.p.get("text", ""), self.fs(size), "black", "text", accent=self.c, maxw=mw)
        self.mark = G.text_sprite("“", self.fs(220), "black", self.c, glow=int(14 * self.u), glow_color=self.c)
        au, ro = self.p.get("author"), self.p.get("role")
        self.au = G.text_sprite(f"— {au}", self.fs(40), "bold", "text") if au else None
        self.ro = G.text_sprite(ro, self.fs(30), "medium", "dim") if ro else None
        ph = self.image(self.p.get("photo"))
        d = int(110 * self.u * self.kz)
        self.av = avatar(ph, d, initials(au), self.c, self.style) if ph is not None else None
        self.t0 = self.at(self.p.get("at", 0), 0.3)
        self.t1 = self.at(self.p.get("author_at"), self.t0 + 0.8)
        lines = [s for s in (self.au, self.ro) if s is not None]
        self.ah = max(sum(s.height for s in lines), self.av.height if self.av is not None else 0)
        mh = self.mark.height * 0.5
        total = mh + self.txt.height + (40 * self.u + self.ah if lines else 0)
        top = a.cy - total / 2
        self.my = top + mh / 2
        self.ty = top + mh + self.txt.height / 2
        self.ay = self.ty + self.txt.height / 2 + 40 * self.u + self.ah / 2

    def draw(self, img, t, T):
        a = self.fade(t)
        a_ = self.area
        km = prog(t, self.t0 - 0.1, self.t0 + 0.45)
        mx = a_.cx - self.txt.width / 2 + self.mark.width * 0.25
        blitc(img, self.mark, max(a_.x0 + self.mark.width / 2, mx), self.my, eo(km) * a, lerp(0.6, 1, eob(km)))
        k = eo(prog(t, self.t0, self.t0 + 0.6))
        blitc(img, self.txt, a_.cx, self.ty + (1 - k) * 36 * self.u, k * a)
        ka = eo(prog(t, self.t1, self.t1 + 0.5))
        if ka <= 0:
            return
        lines = [s for s in (self.au, self.ro) if s is not None]
        w = max([s.width for s in lines] or [0]) + (self.av.width + 24 * self.u if self.av is not None else 0)
        x = a_.cx - w / 2 + (1 - ka) * 30 * self.u
        if self.av is not None:
            blitc(img, self.av, x + self.av.width / 2, self.ay, ka * a)
            x += self.av.width + 24 * self.u
        y = self.ay - sum(s.height for s in lines) / 2
        for s in lines:
            blit(img, s, x, y, ka * a)
            y += s.height


@template("testimonial", aliases=("testimonial",),
          doc="Отзыв клиента: карточка со звёздами (заполняются по одной, бывают половинки), текст, аватар (фото или "
              "инициалы), имя, кто он и откуда отзыв.",
          params={"text": P("Отличный *продукт*", "текст отзыва, *слово* — акцент"),
                  "author": P("Имя Фамилия", "автор"), "role": P(None, "кто он (город, профессия)", str),
                  "photo": P(None, "фото автора (assets/…); нет — инициалы", str),
                  "rating": P(5, "оценка 0–5 (можно 4.5)", NUM),
                  "source": P(None, "откуда отзыв (Google, App Store…)", str),
                  "at": P(0, "появление карточки: бит | '1.5s' | слово озвучки", AT),
                  "color": KitTemplate.COMMON["color"]},
          beats="карточка — с `at`, звёзды — по одной следом, автор — через 0,6 с")
class Testimonial(KitTemplate):
    def setup(self):
        a = self.area
        self.cw = int(min(a.w, 1180 * self.u))
        pad = int(56 * self.u)
        inner = self.cw - 2 * pad
        self.txt = G.text_sprite(self.p.get("text", ""), self.fs(46), "bold", "text", accent=self.c,
                                 align="left", maxw=inner)
        sd = int(54 * self.u * self.kz)
        r = max(0.0, min(5.0, float(self.p.get("rating", 5))))
        self.stars = [(star(sd, "amber", min(1.0, max(0.0, r - i)), self.style), star(sd, "amber", 0.0, self.style))
                      for i in range(5)]
        self.sd = sd
        au = self.p.get("author") or ""
        self.au = G.text_sprite(au, self.fs(38), "black", "text")
        line2 = " · ".join(x for x in (self.p.get("role"), self.p.get("source")) if x)
        self.ro = G.text_sprite(line2, self.fs(28), "medium", "dim", maxw=int(inner * 0.8)) if line2 else None
        ad = int(96 * self.u * self.kz)
        self.av = avatar(self.image(self.p.get("photo")), ad, initials(au), self.c, self.style)
        ah = max(ad, self.au.height + (self.ro.height if self.ro is not None else 0))
        ch = pad + sd + int(30 * self.u) + self.txt.height + int(40 * self.u) + ah + pad
        ch = int(min(ch, a.h))
        self.card = G.panel(self.cw, ch, int(32 * self.u), border=self.c, glow=int(12 * self.u),
                            bw=max(2, int(3 * self.u)), fill_alpha=215)
        self.cpad = (self.card.width - self.cw) // 2
        self.ch, self.pad, self.ah = ch, pad, ah
        self.x0, self.y0 = a.cx - self.cw / 2, a.cy - ch / 2
        self.t0 = self.at(self.p.get("at", 0), 0.2)

    def draw(self, img, t, T):
        a = self.fade(t)
        k = eo(prog(t, self.t0, self.t0 + 0.5))
        if k <= 0:
            return
        dy = (1 - k) * 50 * self.u
        x0, y0 = self.x0, self.y0 + dy
        blit(img, self.card, x0 - self.cpad, y0 - self.cpad, k * a)
        x, y = x0 + self.pad, y0 + self.pad
        for i, (on, off) in enumerate(self.stars):
            ks = prog(t, self.t0 + 0.35 + 0.12 * i, self.t0 + 0.6 + 0.12 * i)
            cx = x + self.sd * (i + 0.5) + 10 * self.u * i
            blitc(img, off, cx, y + self.sd / 2, k * a * 0.6)
            if ks > 0:
                blitc(img, on, cx, y + self.sd / 2, a * eo(ks), lerp(0.5, 1, eob(ks)))
        y += self.sd + 30 * self.u
        blit(img, self.txt, x - self.fs(46) * 0.15, y, k * a)  # у спрайта поле 0,15 кегля слева
        y += self.txt.height + 40 * self.u
        ka = eo(prog(t, self.t0 + 0.6, self.t0 + 1.1))
        blitc(img, self.av, x + self.av.width / 2, y + self.ah / 2, ka * a)
        tx = x + self.av.width + 26 * self.u
        h = self.au.height + (self.ro.height if self.ro is not None else 0)
        blit(img, self.au, tx, y + self.ah / 2 - h / 2, ka * a)
        if self.ro is not None:
            blit(img, self.ro, tx, y + self.ah / 2 - h / 2 + self.au.height, ka * a)
