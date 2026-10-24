"""Пакет kit: lower_third, cta_end, chapter_bumper — плашка с именем, финальный призыв, перебивка главы (ROADMAP C4)."""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ... import assets as AS
from ... import gfx as G
from ... import media as MD
from ...brand import path as brand_path
from ...gfx import blit, blitc, eio, eo, eob, lerp, prog
from ..media.base import kb_curve, window
from ..registry import AT, P, template
from .base import Ink, KitTemplate, circle


@template("lower_third", aliases=("lower_third",),
          doc="Плашка «имя и кто он» внизу слева (или справа): полоса цвета акцента вырастает, имя выезжает из-за "
              "неё, роль — следом; уходит в обратном порядке. Опц. фото на весь кадр под плашкой (медленный наезд).",
          params={"name": P("Имя Фамилия", "имя"), "role": P(None, "кто он (вторая строка)", str),
                  "side": P("left", "left | right"),
                  "file": P(None, "фото на весь кадр под плашкой (assets/…); нет — фон ролика", str),
                  "at": P(0.3, "появление: бит | '1.5s' | слово озвучки", AT),
                  "until": P(None, "уход: бит | '4s' | слово (по умолчанию — держится до конца сцены)", AT),
                  "color": KitTemplate.COMMON["color"]},
          beats="плашка — с `at`, уходит с `until`")
class LowerThird(KitTemplate):
    def setup(self):
        a = self.area
        mw = int(a.w * (0.86 if self.vert else 0.5))
        self.nm = G.text_sprite(self.p.get("name", ""), self.fs(56), "black", "text", align="left", maxw=mw)
        ro = self.p.get("role")
        self.ro = G.text_sprite(ro, self.fs(34), "semibold", "dim", align="left", maxw=mw) if ro else None
        self.pad = int(26 * self.u)
        w = max(self.nm.width, self.ro.width if self.ro is not None else 0) + 2 * self.pad
        h = self.nm.height + (self.ro.height if self.ro is not None else 0) + 2 * self.pad
        self.plate = G.rrect((int(w), int(h)), int(14 * self.u), self.style.col("panel", 225))
        self.bar_w = max(6, int(12 * self.u))
        self.right = self.p.get("side") == "right"
        gap = int(12 * self.u)
        tot = self.bar_w + gap + w
        self.x0 = a.x1 - tot if self.right else a.x0
        self.y1 = a.y1 - 10 * self.u
        self.y0 = self.y1 - h
        self.gap = gap
        self.t0 = self.at(self.p.get("at", 0.3), 0.3)
        u = self.p.get("until")
        self.t1 = self.at(u, self.D) if u is not None else self.D + 1
        self.bg = None
        f = self.p.get("file")
        if f:
            img = MD.image(AS.path(self.roots, f))
            Z = 1.08
            self.bg = MD.cover(img, int(self.W * Z), int(self.H * Z))
            self.shade = Image.new("RGBA", (self.W, self.H // 2), (0, 0, 0, 0))
            grad = Image.linear_gradient("L").resize((self.W, self.H // 2)).point(lambda v: int(v * 0.75))
            sh = Image.new("RGBA", (self.W, self.H // 2), tuple(self.style.pal["bg_top"][:3]) + (255,))
            sh.putalpha(grad)
            self.shade = sh

    def draw_bg(self, img, t):
        if self.bg is None:
            return
        k = kb_curve(t, self.D)
        img.alpha_composite(window(self.bg, self.W, self.H, lerp(1.0, 1.08, k), 0.0, lerp(0.2, -0.2, k)).convert("RGBA"))
        blit(img, self.shade, 0, self.H - self.shade.height, 1.0)

    def draw_plate(self, img, t):
        kin = eio(prog(t, self.t0, self.t0 + 0.35))
        kout = eio(prog(t, self.t1, self.t1 + 0.35))
        kb = kin * (1 - kout)
        if kb <= 0:
            return
        h = self.plate.height
        with Ink(img) as d:
            bx = self.x0 if not self.right else self.x0 + self.gap + self.plate.width
            bh = h * kb
            d.rectangle((bx, self.y1 - bh, bx + self.bar_w, self.y1), fill=self.style.col(self.c))
            kp = eo(prog(t, self.t0 + 0.2, self.t0 + 0.65)) * (1 - eio(prog(t, self.t1 - 0.2, self.t1 + 0.15)))
            if kp <= 0:
                return
            w = int(self.plate.width * kp)
            if w < 2:
                return
            px = bx - self.gap - w if self.right else bx + self.bar_w + self.gap  # плашка выезжает из-за полосы
            layer = self.plate.copy()
            layer.alpha_composite(self.nm, (self.pad - int(self.fs(56) * 0.15), self.pad))
            if self.ro is not None:
                kr = eo(prog(t, self.t0 + 0.45, self.t0 + 0.85))
                if kr > 0:
                    layer.alpha_composite(G.with_alpha(self.ro, kr), (self.pad - int(self.fs(34) * 0.15), self.pad + self.nm.height))
            crop = layer.crop((0, 0, w, h)) if not self.right else layer.crop((self.plate.width - w, 0, self.plate.width, h))
            blit(img, crop, px, self.y0, 1.0)

    def draw(self, img, t, T):
        self.draw_bg(img, t)
        self.draw_plate(img, t)

    def safe_draw(self, img, t, T):
        """Фото на весь кадр — подложка (под обрез можно, как у media), safezone проверяет плашку."""
        self.draw_plate(img, t)


@template("cta_end", aliases=("cta_end",),
          doc="Финальный призыв: логотип (файл или бренд-кит), заголовок, кнопка с пульсом и кликом курсора "
              "(текст меняется на done), ник канала; опц. места под «смотрите дальше» (конечная заставка YouTube). "
              "Держится до конца ролика.",
          params={"title": P("Спасибо, что *досмотрели*", "заголовок, *слово* — акцент"),
                  "button": P("Подписаться", "текст кнопки"), "done": P(None, "текст кнопки после клика", str),
                  "handle": P(None, "ник канала или сайт под кнопкой", str),
                  "logo": P(None, "логотип (assets/…); нет — из бренд-кита, если он есть", str),
                  "next": P(0, "мест под «смотрите дальше» (0–2): рамки конечной заставки", int),
                  "next_label": P("Смотрите дальше", "подпись рамок «смотрите дальше»"),
                  "at": P(0, "появление: бит | '1.5s' | слово озвучки", AT),
                  "click_at": P(None, "клик по кнопке (по умолчанию — через 1,2 с после появления; false — без клика)", AT),
                  "color": KitTemplate.COMMON["color"]},
          beats="всё — с `at`, кнопка пульсирует, клик — `click_at`")
class CtaEnd(KitTemplate):
    def setup(self):
        a = self.area
        nn = max(0, min(2, int(self.p.get("next", 0) or 0)))
        self.side = nn and not self.vert  # широкий кадр: призыв слева, рамки справа
        cw = a.w * (0.5 if self.side else 1.0)
        mw = int(cw * 0.9)
        self.logo = self._logo(int(cw * 0.42), int(a.h * 0.16))
        self.ttl = G.text_sprite(self.p.get("title", ""), self.fs(68), "black", "text", accent=self.c, maxw=mw)
        bf = self.fs(46)
        self.btn = self._button(self.p.get("button", ""), self.c, "bg_top", bf)
        dn = self.p.get("done")
        self.btn_done = self._button(dn, "dim", "text", bf) if dn else None
        hd = self.p.get("handle")
        self.hd = G.text_sprite(hd, self.fs(36), "semibold", "dim") if hd else None
        parts = [s for s in (self.logo, self.ttl, self.btn, self.hd) if s is not None]
        gap = 34 * self.u
        H = sum(s.height for s in parts) + gap * (len(parts) - 1)
        self.boxes = []
        if nn:
            lbl = G.text_sprite(self.p.get("next_label", ""), self.fs(30), "bold", "dim")
            if self.side:
                bw = min(a.w * 0.4, (a.h - 40 * self.u * (nn - 1)) / nn * 16 / 9)
                bh = bw * 9 / 16
                tot = nn * bh + (nn - 1) * 40 * self.u
                bx = a.x1 - bw
                by = a.cy - tot / 2
                self.boxes = [(bx, by + i * (bh + 40 * self.u), bw, bh) for i in range(nn)]
            else:
                bw = min(a.w * 0.8, (a.h - H - 60 * self.u) * 16 / 9 / nn) if nn else 0
                bh = bw * 9 / 16
                H += 60 * self.u + nn * bh + (nn - 1) * 30 * self.u
            self.lbl = lbl
        cx = a.x0 + cw / 2 if self.side else a.cx
        y = a.cy - H / 2
        self.pos = []
        for s in parts:
            self.pos.append((s, cx, y + s.height / 2))
            y += s.height + gap
        if nn and not self.side:
            y += 60 * self.u - gap
            self.boxes = [(cx - bw / 2, y + i * (bh + 30 * self.u), bw, bh) for i in range(nn)]
        self.t0 = self.at(self.p.get("at", 0), 0.2)
        ck = self.p.get("click_at")
        self.tc = None if ck is False else self.at(ck, self.t0 + 1.2)
        self.cursor = self._cursor(int(64 * self.u))
        self.ring = circle(int(70 * self.u), None, outline=self.style.col("text"), width=max(2, int(4 * self.u)))

    def _logo(self, mw, mh):
        f = self.p.get("logo")
        img = None
        if f:
            img = MD.image(AS.path(self.roots, f))
        elif self.style.brand and (self.style.brand.get("logo") or {}).get("light"):
            img = MD.image(brand_path(self.style.brand["logo"]["light"]))
        if img is None:
            return None
        k = min(mw / img.width, mh / img.height)
        return img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)

    def _button(self, text, fill, color, f):
        tx = G.text_sprite(str(text), f, "black", color)
        w, h = int(tx.width + 90 * self.u), int(tx.height + 40 * self.u)
        b = G.rrect((w, h), h // 2, self.style.col(fill))
        b.alpha_composite(tx, ((w - tx.width) // 2, (h - tx.height) // 2))
        return G.glowify(b, fill, 14 * self.u, 0.8) if fill != "dim" else b

    def _cursor(self, s):
        S = s * 3
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pts = [(S * .1, S * .05), (S * .1, S * .8), (S * .3, S * .62), (S * .45, S * .95), (S * .58, S * .9),
               (S * .44, S * .58), (S * .7, S * .58)]
        d.polygon(pts, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=S // 24)
        return img.resize((s, s), Image.LANCZOS)

    def draw(self, img, t, T):
        a = 1.0 if self.last else 1 - prog(t, self.D - 0.35, self.D)
        bi = None
        for i, (s, x, y) in enumerate(self.pos):
            k = prog(t, self.t0 + 0.12 * i, self.t0 + 0.12 * i + 0.5)
            if k <= 0:
                continue
            if s is self.btn:
                bi = (x, y)
                clicked = self.tc is not None and t >= self.tc
                if clicked and self.btn_done is not None:
                    blitc(img, self.btn_done, x, y, a, lerp(0.92, 1, eob(prog(t, self.tc, self.tc + 0.3))))
                    continue
                pulse = 1 + 0.03 * math.sin((t - self.t0) * 2 * math.pi / 1.2) * (0 if clicked else 1)
                press = 1 - 0.08 * (1 - abs(2 * prog(t, self.tc, self.tc + 0.24) - 1)) if self.tc is not None and \
                    self.tc <= t < self.tc + 0.24 else 1.0
                blitc(img, s, x, y, eo(k) * a, lerp(0.7, 1, eob(k)) * pulse * press)
            else:
                blitc(img, s, x, y + (1 - eo(k)) * 30 * self.u, eo(k) * a)
        if bi is not None and self.tc is not None:
            kc = eio(prog(t, self.tc - 0.7, self.tc))
            ka = prog(t, self.tc - 0.8, self.tc - 0.5) * (1 - prog(t, self.tc + 0.6, self.tc + 0.9))
            if ka > 0:
                x = lerp(bi[0] + self.btn.width * 0.6, bi[0] + self.btn.width * 0.12, kc)
                y = lerp(bi[1] + self.btn.height * 1.1, bi[1] + self.btn.height * 0.05, kc)
                rk = prog(t, self.tc, self.tc + 0.5)
                if 0 < rk < 1:
                    blitc(img, self.ring, x, y, (1 - rk) * a, 0.5 + rk)
                blit(img, self.cursor, x - self.cursor.width * 0.1, y - self.cursor.height * 0.05, ka * a)
        ks = [eo(prog(t, self.t0 + 0.3 + 0.15 * j, self.t0 + 0.8 + 0.15 * j)) for j in range(len(self.boxes))]
        with Ink(img) as d:  # рамки — до значков и подписей на них
            for (x, y, w, h), k in zip(self.boxes, ks):
                if k > 0:
                    d.rounded_rectangle((x, y, x + w, y + h), int(20 * self.u), fill=self.style.col("panel", int(200 * k * a)),
                                        outline=self.style.col("dim", int(200 * k * a)), width=max(2, int(3 * self.u)))
        for (x, y, w, h), k in zip(self.boxes, ks):
            if k > 0:
                blitc(img, G.icon("play", int(h * 0.3), self.c, glow=False), x + w / 2,
                      y + h / 2 - self.lbl.height * 0.4, k * a)
                blitc(img, self.lbl, x + w / 2, y + h * 0.78, k * a)


@template("chapter_bumper", aliases=("chapter_bumper",),
          doc="Перебивка главы (1,5–3 с) для любой палитры: полоса цвета акцента проносится через кадр, номер главы "
              "крупно со свечением, надзаголовок и название; уходит полосой в другую сторону.",
          params={"number": P(1, "номер главы (число или строка)", (int, str)),
                  "title": P("Название главы", "название, *слово* — акцент"),
                  "kicker": P("Глава", "надзаголовок над номером"),
                  "total": P(None, "всего глав: подпись «1 / 5»", int),
                  "at": P(0, "начало: бит | '1.5s' | слово озвучки", AT),
                  "color": KitTemplate.COMMON["color"]},
          beats="всё — с `at`; уход — в последние 0,5 с сцены")
class ChapterBumper(KitTemplate):
    def setup(self):
        a = self.area
        n = self.p.get("number", 1)
        tot = self.p.get("total")
        self.num = G.text_sprite(f"{int(n):02d}" if isinstance(n, int) else str(n), self.fs(230), "black", self.c,
                                 glow=int(26 * self.u), glow_color=self.c, family="num")
        kk = self.p.get("kicker")
        kick = f"{kk}  ·  {n} / {tot}" if (kk and tot) else (kk or (f"{n} / {tot}" if tot else ""))
        self.kk = G.text_sprite(str(kick).upper(), self.fs(36), "bold", "dim", tracking=0.18) if kick else None
        self.tt = G.text_sprite(self.p.get("title", ""), self.fs(78), "black", "text", accent=self.c,
                                maxw=int(a.w * 0.9))
        parts = [s for s in (self.kk, self.num, self.tt) if s is not None]
        H = sum(s.height for s in parts) + 10 * self.u * (len(parts) - 1)
        y = a.cy - H / 2
        self.pos = []
        for s in parts:
            self.pos.append((s, y + s.height / 2))
            y += s.height + 10 * self.u
        self.t0 = self.at(self.p.get("at", 0), 0.0)
        self.band_h = int(min(a.h * 0.42, self.fs(230) * 0.95))  # спрайт номера выше глифа: поля под свечение

    def draw(self, img, t, T):
        a = self.area
        ki = eio(prog(t, self.t0, self.t0 + 0.45))
        ko = eio(prog(t, self.D - 0.5, self.D - 0.1)) if not self.last else 0.0
        if ki > 0 and ko < 1:  # полоса: вход слева направо, уход — направо
            x0 = lerp(a.x0, a.x1, ko)
            x1 = lerp(a.x0, a.x1, ki)
            cy = self.pos[1][1] if len(self.pos) > 1 else a.cy
            if x1 - x0 > 1:
                with Ink(img) as d:
                    d.rectangle((x0, cy - self.band_h / 2, x1, cy + self.band_h / 2),
                                fill=self.style.col(self.c, int(46 * (1 - ko))))
                    d.rectangle((x0, cy + self.band_h / 2 - max(2, 5 * self.u), x1, cy + self.band_h / 2),
                                fill=self.style.col(self.c, int(230 * (1 - ko))))
        out = 1 - eo(prog(t, self.D - 0.45, self.D - 0.05)) if not self.last else 1.0
        for i, (s, y) in enumerate(self.pos):
            k = prog(t, self.t0 + 0.15 + 0.12 * i, self.t0 + 0.65 + 0.12 * i)
            if k <= 0:
                continue
            if s is self.num:
                blitc(img, s, a.cx, y, eo(k) * out, lerp(1.25, 1, eo(k)))
            else:
                blitc(img, s, a.cx + (1 - eo(k)) * 50 * self.u * (1 if i else -1), y, eo(k) * out)

