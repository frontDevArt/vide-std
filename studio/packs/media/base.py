"""Пакет media: база шаблонов с фото и видео — рамка, маска формы, вход/выход, подпись, триггеры `at`."""
from __future__ import annotations

import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ... import assets as AS
from ... import gfx as G
from ...gfx import blit, eio, eo, lerp, prog
from ..base import Box, Template
from ..lab.triggers import SECONDS, word_time
from ..registry import AT, NUM, P

FRAME = "кадр целиком"


class MediaTemplate(Template):
    """Фото/видео в рамке `box` (доли рабочей зоны шаблона; нет — весь кадр под обрез), форма `shape`, вход `enter`,
    подпись `caption` (+ `kicker`) с бита `caption_at`. Файлы — пути от папки проекта (assets/…, studio/assets.py)."""
    COMMON = {
        "box": P(None, f"рамка [x0, y0, x1, y1] в долях рабочей зоны (без полосы субтитров); нет — {FRAME}", list),
        "shape": P("rect", "форма: rect | round (радиус бренд-кита) | circle"),
        "border": P(False, "обводка цветом accent"),
        "enter": P(None, "вход: cut | fade | rise | zoom (по умолчанию: весь кадр — cut, рамка — rise)", str),
        "exit": P(None, "выход: cut | fade (по умолчанию: весь кадр — cut, рамка — fade)", str),
        "caption": P(None, "подпись, *слово* — акцент", str),
        "kicker": P(None, "надпись над подписью (мелко, accent2)", str),
        "caption_at": P(0, "когда появляется подпись: бит | '1.5s' | слово озвучки", AT),
        "dim": P(None, "затемнение низа кадра под подпись 0–1 (по умолчанию 0,72 при подписи на весь кадр)", NUM),
    }

    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        self.roots = ctx.get("roots") or ["."]
        self.words = scene.get("words") or []
        b = self.p.get("box")
        self.full = not b
        if self.full:
            self.box = Box(0, 0, self.W, self.H)
        else:
            a = self.area
            x0, y0, x1, y1 = (float(v) for v in b)
            self.box = Box(round(a.x0 + a.w * x0), round(a.y0 + a.h * y0), round(a.x0 + a.w * x1), round(a.y0 + a.h * y1))
        self.bw, self.bh = max(2, int(self.box.w)), max(2, int(self.box.h))

    # ---------- файлы и время
    def src(self, rel):
        return AS.path(self.roots, rel)

    def at(self, spec, default=0.0):
        """Бит (int) | секунды (float, '1.5s') | слово озвучки (строка, как у lab: 'word#2') → время сцены."""
        if spec is None or isinstance(spec, bool):
            return default
        if isinstance(spec, int):
            return max(0.0, self.bt(spec, default) - 0.1) if self.beats else default
        if isinstance(spec, float):
            return spec
        m = SECONDS.fullmatch(str(spec).strip())
        if m:
            return float(m.group(1))
        t, _ = word_time(self.words, spec)
        return max(0.0, t - 0.1) if t is not None else default

    # ---------- форма, тень, вход и выход
    def radius(self):
        r = self.style.shape.get("radius")
        return int((r if r is not None else 28) * self.u)

    def mask(self):
        """Маска формы рамки (L, bw×bh) или None для rect."""
        sh = self.p.get("shape", "rect")
        if sh == "round":
            return G.rr_mask(self.bw, self.bh, self.radius())
        if sh == "circle":
            m = Image.new("L", (self.bw * 4, self.bh * 4), 0)
            ImageDraw.Draw(m).ellipse((0, 0, self.bw * 4 - 1, self.bh * 4 - 1), fill=255)
            return m.resize((self.bw, self.bh), Image.LANCZOS)
        return None

    def setup_frame(self):
        """Маска, обводка и тень рамки — один раз."""
        self.mk = self.mask()
        self.edge = None
        if self.p.get("border"):
            w = max(2, int(4 * self.u))
            e = Image.new("RGBA", (self.bw, self.bh), (0, 0, 0, 0))
            d = ImageDraw.Draw(e)
            if self.p.get("shape") == "circle":
                d.ellipse((w // 2, w // 2, self.bw - w // 2 - 1, self.bh - w // 2 - 1), outline=self.style.col("accent"), width=w)
            else:
                r = self.radius() if self.p.get("shape") == "round" else 0
                d.rounded_rectangle((w // 2, w // 2, self.bw - w // 2 - 1, self.bh - w // 2 - 1), r,
                                    outline=self.style.col("accent"), width=w)
            self.edge = e
        self.shadow = None
        if not self.full:
            pad = int(40 * self.u)
            s = Image.new("RGBA", (self.bw + 2 * pad, self.bh + 2 * pad), (0, 0, 0, 0))
            m = self.mk if self.mk is not None else Image.new("L", (self.bw, self.bh), 255)
            a = Image.new("L", s.size, 0)
            a.paste(m.point(lambda v: v * 150 // 255), (pad, pad + int(12 * self.u)))
            s.putalpha(a.filter(ImageFilter.GaussianBlur(18 * self.u)))
            self.shadow, self.pad = s, pad

    def mode(self, which):
        v = self.p.get(which)
        if v:
            return v
        return "cut" if self.full else ("rise" if which == "enter" else "fade")

    def envelope(self, t):
        """(альфа, масштаб, сдвиг по y) входа и выхода."""
        a, sc, dy = 1.0, 1.0, 0.0
        en = self.mode("enter")
        k = eo(prog(t, 0.0, 0.45))
        if en == "fade":
            a = k
        elif en == "rise":
            a, dy = k, (1 - k) * 60 * self.u
        elif en == "zoom":
            a, sc = k, lerp(0.88, 1.0, k)
        if self.mode("exit") == "fade" and not self.last:
            a = min(a, 1 - prog(t, self.D - 0.3, self.D))
        return a, sc, dy

    def put(self, img, content, t):
        """Содержимое рамки (RGBA bw×bh) → кадр: маска, обводка, тень, вход/выход."""
        if self.mk is not None:
            content.putalpha(ImageChops.darker(content.getchannel("A"), self.mk))
        if self.edge is not None:
            content.alpha_composite(self.edge)
        a, sc, dy = self.envelope(t)
        if a <= 0.004:
            return
        if self.shadow is not None:
            G.blitc(img, self.shadow, self.box.cx, self.box.cy + dy, a, sc)
        if abs(sc - 1) < 0.004:
            blit(img, content, self.box.x0, self.box.y0 + dy, a)
        else:
            G.blitc(img, content, self.box.cx, self.box.cy + dy, a, sc)

    # ---------- кадр: подложка (фото/видео) и то, что поверх
    def draw(self, img, t, T):
        self.draw_media(img, t)
        self.draw_over(img, t)

    def safe_draw(self, img, t, T):
        """Фото на весь кадр — подложка (под обрез можно), safezone проверяет только то, что поверх; в рамке — всё."""
        if self.full:
            self.draw_over(img, t)
        else:
            self.draw(img, t, T)

    def draw_media(self, img, t):
        raise NotImplementedError

    def draw_over(self, img, t):
        self.draw_caption(img, t)

    # ---------- подпись
    def setup_caption(self):
        cap, kick = self.p.get("caption"), self.p.get("kicker")
        self.cap = self.kick = self.shade = None
        if not (cap or kick):
            return
        k = 1.0 if self.vert else 1.1
        mw = int(self.area.w * 0.9)
        if cap:
            self.cap = G.text_sprite(cap, int(64 * self.u * k), "black", "text", maxw=mw)
        if kick:
            self.kick = G.text_sprite(kick, int(40 * self.u * k), "bold", "accent2", maxw=mw)
        self.t_cap = self.at(self.p.get("caption_at", 0), 0.35)
        dim = self.p.get("dim")
        dim = (0.72 if self.full else 0.0) if dim is None else float(dim)
        if dim > 0:  # затемнение к цвету фона от чуть выше подписи до низа кадра — подпись читается на любом фото
            hh = sum(s.height for s in (self.cap, self.kick) if s is not None)
            top = max(0, int(self.caption_y() - hh - 0.22 * self.H))
            h = self.H - top
            ramp = Image.linear_gradient("L").resize((1, 256)).point(lambda v: int(255 * dim * min(1.0, v / 255 / 0.45)))
            sh = Image.new("RGBA", (self.W, h), tuple(self.style.pal.get("bg", self.style.pal["bg_top"]))[:3] + (255,))
            sh.putalpha(ramp.resize((self.W, h), Image.BILINEAR))
            self.shade = sh

    def caption_y(self):
        """Низ подписи: весь кадр — низ рабочей зоны; рамка — под рамкой, если влезает, иначе внутри низа рамки."""
        hh = sum(s.height for s in (self.cap, self.kick) if s is not None)
        if self.full:
            return self.area.y1 - 20 * self.u
        below = self.box.y1 + 30 * self.u + hh
        return below if below <= self.area.y1 else self.box.y1 - 24 * self.u

    def caption_alpha(self, t):
        return self.envelope(t)[0] if not self.full else (1.0 if self.last else 1 - prog(t, self.D - 0.25, self.D))

    def draw_shade(self, img, t):
        """Затемнение низа под подпись — часть подложки (во всю ширину кадра)."""
        if getattr(self, "shade", None) is not None:
            blit(img, self.shade, 0, self.H - self.shade.height, self.caption_alpha(t))

    def draw_caption(self, img, t):
        if self.cap is None and self.kick is None:
            return
        a0 = self.caption_alpha(t)
        k = eo(prog(t, self.t_cap, self.t_cap + 0.5))
        if k <= 0:
            return
        y = self.caption_y()
        if self.cap is not None:
            G.blitc(img, self.cap, self.W / 2, y - self.cap.height / 2 + (1 - k) * 30 * self.u, k * a0)
            y -= self.cap.height + 6 * self.u
        if self.kick is not None:
            kk = eo(prog(t, self.t_cap - 0.15, self.t_cap + 0.35))
            G.blitc(img, self.kick, self.W / 2, y - self.kick.height / 2, kk * a0)


def window(src, bw, bh, z, cx, cy):
    """Окно масштаба z (≥ 1) с центром (cx, cy) в долях свободного хода (−1…1) картинки src → bw×bh.
    src подготовлен под наибольший масштаб: src.size = (bw, bh) × S; окно = (bw, bh) × S / z."""
    S = src.width / bw
    ww, wh = bw * S / z, bh * S / z
    sx, sy = (src.width - ww) / 2, (src.height - wh) / 2
    x0 = sx + sx * max(-1.0, min(1.0, cx))
    y0 = sy + sy * max(-1.0, min(1.0, cy))
    return src.resize((bw, bh), Image.BICUBIC, box=(x0, y0, x0 + ww, y0 + wh))


def kb_curve(t, D):
    """Ход Ken Burns: почти равномерно, чуть мягче на краях (на стыке сцен движение не дёргается)."""
    k = max(0.0, min(1.0, t / D)) if D > 0 else 1.0
    return 0.75 * k + 0.25 * eio(k)


def pan_at(pan, k):
    (x0, y0), (x1, y1) = pan
    return lerp(float(x0), float(x1), k), lerp(float(y0), float(y1), k)


def ease_cos(k):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, k)))
