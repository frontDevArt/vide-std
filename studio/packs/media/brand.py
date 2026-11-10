"""Пакет media: шаблоны бренда — logo_sting (логотип-«стинг»: пружина, свечение, блик, слоган) и product_card
(карточка продукта: фото, название, цена «было → стало», плашка скидки)."""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ... import anim as A
from ... import gfx as G
from ... import media as MD
from ...brand import path as brand_path
from ...gfx import blit, blitc, eio, eo, lerp, prog
from ..commerce.elements import thousands
from ..registry import AT, NUM, P, template
from .base import MediaTemplate, kb_curve, window


def _lum(rgb):
    r, g, b = rgb[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def plate(logo, style, u):
    """Белая карточка под логотипом (радиус бренда) и мягкая тень под ней цветом низа фона — логотип в цветах фона
    (синий на синем) не сливается с ним. Логотип — вариант для светлого фона."""
    pad = int(max(logo.width, logo.height) * 0.16)
    w, h = logo.width + 2 * pad, logo.height + 2 * pad
    r = int(style.shape.get("radius", 28) * 1.6 * u)
    card = G.rrect((w, h), r, (255, 255, 255, 255))
    card.alpha_composite(logo, (pad, pad))
    blur = max(2, int(34 * u))
    sh = Image.new("RGBA", (w + 4 * blur, h + 4 * blur), (0, 0, 0, 0))
    sh.alpha_composite(G.rrect((w, h), r, style.col("bg_bot", 230)), (2 * blur, 2 * blur))
    return card, sh.filter(ImageFilter.GaussianBlur(blur))


@template("logo_sting",
          doc="Логотип-«стинг» (интро/аутро бренда): логотип выпрыгивает пружиной, за ним расходится свечение, по нему "
              "проходит блик, снизу — слоган. Логотип — file или из бренд-кита (light на тёмном фоне, dark на "
              "светлом); нет ни того ни другого — имя бренда текстом.",
          params={"file": P(None, "логотип PNG/JPG (прозрачный фон), путь от папки проекта; нет — из бренд-кита", str),
                  "text": P(None, "логотип текстом, если файла нет (по умолчанию — имя бренд-кита)", str),
                  "tagline": P(None, "слоган под логотипом, *слово* — акцент", str),
                  "size": P(None, "ширина логотипа, доля рабочей зоны (по умолчанию 0,8 в высоком кадре, 0,4 в широком)",
                            NUM),
                  "at": P(0.0, "когда логотип появляется: бит | '1.5s' | слово озвучки", AT),
                  "glow": P(True, "свечение за логотипом цветом accent"),
                  "plate": P(None, "light — логотип для светлого фона на белой карточке с тенью (свечение выключается): "
                                   "логотип в цветах фона не сливается с ним", str),
                  "exit": P(None, "cut | fade (по умолчанию fade, у последней сцены — cut)", str)},
          beats="логотип — с `at` (по умолчанию сразу), блик — через 0,5 с, слоган — через 0,8 с")
class LogoSting(MediaTemplate):
    def setup(self):
        self.full = False  # логотип — содержимое (safezone проверяет его целиком), не подложка
        a = self.area
        size = self.p.get("size") or (0.8 if self.vert else 0.4)
        mw, mh = int(a.w * float(size)), int(a.h * 0.42)
        card = self.p.get("plate") == "light"
        if card:  # логотип с полями карточки (+32 %): по ширине — в прежних пределах, по высоте — до 0,48 зоны
            mw, mh = int(mw * 0.72), int(a.h * 0.36)
        logo = self._logo_image(light_bg=card)
        if logo is not None:
            k = min(mw / logo.width, mh / logo.height)
            self.logo = logo.resize((max(1, int(logo.width * k)), max(1, int(logo.height * k))), Image.LANCZOS)
        else:
            name = self.p.get("text") or (self.style.brand or {}).get("name")
            self.logo = (G.text_sprite(name, int(130 * self.u * (1 if self.vert else 1.15)), "black", "text", maxw=mw)
                         if name else Image.new("RGBA", (1, 1), (0, 0, 0, 0)))  # нечего показать — только слоган
        if card:
            self.logo, self.shadow = plate(self.logo, self.style, self.u)
        else:
            self.shadow = None
        self.halo = G.glowify(Image.new("RGBA", self.logo.size, (0, 0, 0, 0)), "accent", 40 * self.u, 1.0,
                              mask=self.logo.getchannel("A")) if self.p.get("glow", True) and not card else None
        self.tag = (G.text_sprite(self.p["tagline"], int(50 * self.u * (1 if self.vert else 1.1)), "semibold", "text",
                                  maxw=int(a.w * 0.9)) if self.p.get("tagline") else None)
        self.t0 = self.at(self.p.get("at", 0.0), 0.0)
        self.cy = a.cy - (self.tag.height * 0.6 if self.tag is not None else 0)
        self.ring = None

    def _logo_image(self, light_bg=False):
        f = self.p.get("file")
        if f:
            return MD.image(self.src(f))
        kit = (self.style.brand or {}).get("logo") or {}
        bg = self.style.pal.get("bg", self.style.pal.get("bg_top", (0, 0, 0)))
        want = ("light", "dark") if _lum(bg) < 128 and not light_bg else ("dark", "light")
        for k in want:
            if kit.get(k):
                return MD.image(brand_path(kit[k]))
        return None

    def _shine(self, k):
        """Блик по логотипу: диагональная полоса, видна только там, где логотип непрозрачен."""
        w, h = self.logo.size
        band = Image.new("L", (w, h), 0)
        x = lerp(-0.4 * w, 1.4 * w, k)
        ImageDraw.Draw(band).polygon([(x - 0.12 * w, 0), (x + 0.05 * w, 0), (x - 0.05 * w + 0.0, h), (x - 0.22 * w, h)],
                                     fill=170)
        band = band.filter(ImageFilter.GaussianBlur(max(1, 6 * self.u)))
        m = ImageChops.multiply(band, self.logo.getchannel("A"))
        out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        out.putalpha(m)
        return out

    def draw(self, img, t, T):
        x = t - self.t0
        if x < 0:
            return
        ex = self.p.get("exit") or ("cut" if self.last else "fade")
        out = 1 - prog(t, self.D - 0.35, self.D) if ex == "fade" else 1.0
        sc = lerp(0.6, 1.0, A.spring(prog(x, 0.0, 0.7)))
        a = eo(prog(x, 0.0, 0.25)) * out
        cx = self.W / 2
        if self.halo is not None:
            pulse = eo(prog(x, 0.05, 0.9))
            blitc(img, self.halo, cx, self.cy, a * lerp(0.0, 0.9, pulse) * (1 - 0.35 * prog(x, 0.9, 2.0)),
                  sc * lerp(0.8, 1.08, pulse))
        if self.shadow is not None:
            blitc(img, self.shadow, cx, self.cy + 22 * self.u * sc, a * 0.9, sc)
        blitc(img, self.logo, cx, self.cy, a, sc)
        ks = prog(x, 0.5, 1.15)
        if 0 < ks < 1:
            blitc(img, self._shine(eio(ks)), cx, self.cy, a, sc)
        if self.tag is not None:
            k = eo(prog(x, 0.8, 1.3))
            blitc(img, self.tag, cx, self.cy + self.logo.height / 2 + 40 * self.u + self.tag.height / 2
                  + (1 - k) * 24 * self.u, k * out)


@template("product_card",
          doc="Карточка продукта: фото (медленный наезд) в карточке со скруглением бренд-кита, название, цена; старая "
              "цена зачёркивается, новая выпрыгивает пружиной, плашка скидки. 9:16 и 4:5 — фото сверху, 16:9 и 1:1 — "
              "фото слева. Числа ≥ 1000 — с запятыми (как commerce.number).",
          params={"file": P(None, "фото продукта, путь от папки проекта (assets/…)", str),
                  "name": P("Product", "название"),
                  "note": P(None, "строка под названием (свойство, объём…)", str),
                  "price": P(None, "цена (новая)", str),
                  "was": P(None, "старая цена — зачёркивается", str),
                  "badge": P(None, "плашка в углу фото: «−50 %», «NEW»", str),
                  "at": P(0, "когда появляется цена: бит | '1.5s' | слово озвучки", AT),
                  "strike_at": P(None, "когда зачёркивается старая цена (по умолчанию — с ценой)", AT),
                  "zoom": P([1.0, 1.08], "наезд на фото: масштаб в начале и в конце", list),
                  "focus": P([0.5, 0.5], "точка фото, что остаётся в кадре при обрезке", list)},
          beats="карточка — с начала сцены, название — следом, цена — с `at`, зачёркивание — `strike_at`")
class ProductCard(MediaTemplate):
    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        a = self.area
        self.full = False
        if a.w / a.h < 0.9:  # высокая рабочая зона (9:16, 4:5) — фото сверху, во всю ширину карточки
            w = min(a.w * 0.9, a.h * 0.62)
            h = min(a.h * 0.96, w * 1.42)
            self.photo_h = 0.64
        else:  # 16:9 и 1:1 (зона над субтитрами шире, чем высота) — фото слева на 52 % ширины
            w = a.w * (0.78 if self.W > self.H else 0.9)
            h = min(a.h * 0.86, w * 0.62)
            self.photo_h = None
        self.box_card = (a.cx - w / 2, a.cy - h / 2, a.cx + w / 2, a.cy + h / 2)
        self.cw, self.ch = int(w), int(h)

    def setup(self):
        r = self.radius()
        cw, ch = self.cw, self.ch
        if self.photo_h:
            pw, ph = cw, int(ch * self.photo_h)
        else:
            pw, ph = int(cw * 0.52), ch
        self.pw, self.ph = pw, ph
        z = [max(1.0, float(v)) for v in (self.p.get("zoom") or [1.0, 1.0])][:2]
        self.z0, self.z1 = z[0], z[-1]
        f = self.p.get("file")
        self.photo = (MD.fit(MD.image(self.src(f)), round(pw * max(z)), round(ph * max(z)), "cover",
                             tuple(self.p.get("focus") or (0.5, 0.5))) if f else None)
        surf = self.style.pal.get("bg2", self.style.pal.get("panel", (30, 30, 40)))
        self.card = G.rrect((cw, ch), r, tuple(surf)[:3] + (245,))
        m = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, cw - 1, ch - 1), r, fill=255)
        self.card_mask = m
        pad = int(cw * 0.07)
        iw = (cw if self.photo_h else cw - pw) - 2 * pad
        k = 1.0 if self.vert else 1.1
        self.name = G.text_sprite(self.p.get("name", ""), int(62 * self.u * k), "black", "text", maxw=iw, align="left")
        self.note = (G.text_sprite(self.p["note"], int(34 * self.u * k), "medium", "dim", maxw=iw, align="left")
                     if self.p.get("note") else None)
        self.now = (G.text_sprite(thousands(str(self.p["price"])), int(96 * self.u * k), "black", "accent")
                    if self.p.get("price") else None)
        self.was = (G.text_sprite(thousands(str(self.p["was"])), int(48 * self.u * k), "bold", "dim")
                    if self.p.get("was") else None)
        self.badge = None
        if self.p.get("badge"):
            s = G.text_sprite(self.p["badge"], int(40 * self.u * k), "black", "ink" if "ink" in self.style.pal else "bg_top")
            b = G.rrect((s.width + int(30 * self.u), s.height + int(14 * self.u)), int(12 * self.u),
                        self.style.col("accent2"))
            b.alpha_composite(s, (int(15 * self.u), int(7 * self.u)))
            self.badge = b
        self.pad = pad
        self.t_price = self.at(self.p.get("at", 0), 0.8)
        st = self.p.get("strike_at")
        self.t_strike = self.at(st, self.t_price) if st is not None else self.t_price
        pad2 = int(40 * self.u)
        sh = Image.new("RGBA", (cw + 2 * pad2, ch + 2 * pad2), (0, 0, 0, 0))
        al = Image.new("L", sh.size, 0)
        al.paste(m.point(lambda v: v * 140 // 255), (pad2, pad2 + int(14 * self.u)))
        sh.putalpha(al.filter(ImageFilter.GaussianBlur(20 * self.u)))
        self.card_shadow = sh

    def draw(self, img, t, T):
        x0, y0, x1, y1 = self.box_card
        k_in = eo(prog(t, 0.0, 0.5))
        out = 1.0 if self.last else 1 - prog(t, self.D - 0.3, self.D)
        a = k_in * out
        if a <= 0.004:
            return
        c = self.card.copy()
        if self.photo is not None:
            kz = kb_curve(t, self.D)
            ph = window(self.photo, self.pw, self.ph, lerp(self.z0, self.z1, kz), 0.0, 0.0)
            c.alpha_composite(ph, (0, 0))
            c.putalpha(ImageChops.darker(c.getchannel("A"), self.card_mask))
        if self.badge is not None:
            kb = A.spring(prog(t, 0.45, 1.05))
            if kb > 0:
                bb = self.badge.resize((max(1, int(self.badge.width * kb)), max(1, int(self.badge.height * kb))),
                                       Image.BILINEAR)
                c.alpha_composite(bb, (self.pad - (bb.width - self.badge.width) // 2,
                                       self.pad - (bb.height - self.badge.height) // 2))
        ix = self.pad if self.photo_h else self.pw + self.pad
        iy = (self.ph + self.pad * 0.7) if self.photo_h else self.pad * 1.4
        kn = eo(prog(t, 0.25, 0.7))
        G.blit(c, self.name, ix, iy + (1 - kn) * 20 * self.u, kn)
        iy += self.name.height + 6 * self.u
        if self.note is not None:
            G.blit(c, self.note, ix, iy, eo(prog(t, 0.35, 0.8)))
            iy += self.note.height + 10 * self.u
        py = (self.ch - self.pad * 0.8 - (self.now.height if self.now is not None else 0)) if self.photo_h else \
            max(iy + 20 * self.u, self.ch * 0.55)
        px = ix
        if self.was is not None:
            kw = eo(prog(t, 0.4, 0.8))
            wy = py + ((self.now.height - self.was.height) * 0.62 if self.now is not None else 0)
            G.blit(c, self.was, px, wy, kw)
            ks = eio(prog(t, self.t_strike, self.t_strike + 0.35))
            if ks > 0:
                d = ImageDraw.Draw(c)
                ly = wy + self.was.height * 0.52
                d.line((px + self.was.width * 0.06, ly, px + self.was.width * (0.06 + 0.86 * ks), ly - 2 * self.u),
                       fill=self.style.col("accent2"), width=max(3, int(6 * self.u)))
            px += self.was.width + 24 * self.u
        if self.now is not None:
            kp = prog(t, self.t_price, self.t_price + 0.6)
            if kp > 0:
                s = lerp(0.4, 1.0, A.spring(kp))
                G.blitc(c, self.now, px + self.now.width / 2, py + self.now.height / 2, eo(prog(kp, 0, 0.3)), s)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + (1 - k_in) * 50 * self.u
        blitc(img, self.card_shadow, cx, cy, a)
        blitc(img, c, cx, cy, a, lerp(0.96, 1.0, k_in))
