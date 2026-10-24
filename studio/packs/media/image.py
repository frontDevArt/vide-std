"""Пакет media: шаблон image — фото с Ken Burns, параллаксом по слоям, проявлением по маске, «до → после»."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFilter

from ... import gfx as G
from ... import media as MD
from ...gfx import eio, eo, lerp, prog
from ..registry import AT, P, template
from .base import MediaTemplate, kb_curve, pan_at, window

MOTIONS = ("kenburns", "parallax", "reveal", "before_after", "none")


@template("image",
          doc="Фото: Ken Burns (медленный наезд и панорама), параллакс 2.5D по слоям (фон и вырезанный объект PNG), "
              "проявление по маске (шторка или круг), «до → после» шторкой. Весь кадр под обрез или рамка с формой, "
              "подпись снизу.",
          params={"file": P(None, "фото, путь от папки проекта (assets/…)", str),
                  "layers": P(None, "parallax: слои от дальнего к ближнему [{file, depth 0–1, fit: cover|contain, "
                                    "focus: [x, y]}] — объект — PNG с прозрачностью", list),
                  "after": P(None, "before_after: второе фото (после)", str),
                  "motion": P("kenburns", "kenburns | parallax | reveal | before_after | none"),
                  "zoom": P([1.04, 1.14], "масштаб в начале и в конце сцены (≥ 1)", list),
                  "pan": P([[-0.5, 0.3], [0.5, -0.3]], "центр окна в начале и в конце, доли свободного хода −1…1", list),
                  "fit": P("cover", "cover — под обрез | contain — целиком"),
                  "focus": P([0.5, 0.5], "точка фото, что остаётся в кадре при обрезке (доли)", list),
                  "at": P(0, "reveal / before_after: бит | '1.5s' | слово озвучки", AT),
                  "reveal": P("wipe", "reveal: wipe (шторка слева направо) | circle (круг из центра)"),
                  "labels": P(None, "before_after: ярлыки [до, после]", list),
                  **MediaTemplate.COMMON},
          beats="движение — на всю сцену; reveal и before_after — с `at` (бит, секунды или слово), подпись — с "
                "`caption_at`. Без голоса битов нет: `at: '1.2s'`")
class ImageScene(MediaTemplate):
    def setup(self):
        m = self.p.get("motion", "kenburns")
        self.motion = m if m in MOTIONS else "kenburns"
        z = [float(v) for v in (self.p.get("zoom") or [1.0, 1.0])][:2]
        self.z0, self.z1 = max(1.0, z[0]), max(1.0, z[-1])
        if self.motion in ("none", "before_after"):
            self.z0 = self.z1 = 1.0
        self.pan = self.p.get("pan") or [[0, 0], [0, 0]]
        self.layers = []
        specs = self.p.get("layers") if self.motion == "parallax" and self.p.get("layers") else [
            {"file": self.p.get("file"), "depth": 1.0, "fit": self.p.get("fit", "cover"), "focus": self.p.get("focus")}]
        for sp in specs:
            if not sp.get("file"):
                continue
            d = float(sp.get("depth", 1.0))
            # слой ближе — сильнее масштаб и сдвиг; запас m — чтобы было куда сдвигать и при масштабе 1
            m = 0.05 + 0.10 * d if self.motion == "parallax" else 0.0
            zl0, zl1 = (1 + (self.z0 - 1) * (0.5 + d), 1 + (self.z1 - 1) * (0.5 + d)) if self.motion == "parallax" \
                else (self.z0, self.z1)
            S = max(zl0, zl1) * (1 + m)
            img = MD.fit(MD.image(self.src(sp["file"])), round(self.bw * S), round(self.bh * S),
                         sp.get("fit", "cover"), tuple(sp.get("focus") or (0.5, 0.5)))
            self.layers.append({"img": img, "d": d, "m": m, "z": (zl0, zl1)})
        self.after = None
        if self.motion == "before_after" and self.p.get("after"):
            self.after = MD.fit(MD.image(self.src(self.p["after"])), self.bw, self.bh, self.p.get("fit", "cover"),
                                tuple(self.p.get("focus") or (0.5, 0.5)))
        self.t_at = self.at(self.p.get("at", 0), 0.4)
        self.lab = None
        if self.motion == "before_after" and self.p.get("labels"):
            a, b = (list(self.p["labels"]) + ["", ""])[:2]
            self.lab = [self._chip(a, "dim"), self._chip(b, "accent")]
        self.setup_frame()
        self.setup_caption()

    def _chip(self, text, color):
        if not text:
            return None
        s = G.text_sprite(str(text), int(34 * self.u), "bold", "text")
        pad = int(14 * self.u)
        chip = G.rrect((s.width + 2 * pad, s.height + pad), int(s.height * 0.5), self.style.col("bg_top", 200))
        chip.alpha_composite(s, (pad, pad // 2))
        bar = G.rrect((chip.width, max(3, int(5 * self.u))), 2, self.style.col(color))
        chip.alpha_composite(bar, (0, chip.height - bar.height))
        return chip

    def content(self, t):
        k = kb_curve(t, self.D)
        cx, cy = pan_at(self.pan, k)
        out = Image.new("RGBA", (self.bw, self.bh), (0, 0, 0, 0))
        for L in self.layers:
            zl = lerp(L["z"][0], L["z"][1], k) * (1 + L["m"])
            if self.motion == "parallax":
                c = (cx * L["d"], cy * L["d"])
            else:
                c = (cx, cy)
            out.alpha_composite(window(L["img"], self.bw, self.bh, zl, *c))
        return out

    def draw_media(self, img, t):
        c = self.content(t)
        if self.motion == "reveal":
            c.putalpha(self._reveal(c.getchannel("A"), eio(prog(t, self.t_at, self.t_at + 0.8))))
        elif self.motion == "before_after" and self.after is not None:
            k = eio(prog(t, self.t_at, self.t_at + 0.9))
            x = int(self.bw * k)
            if x > 0:
                c.paste(self.after.crop((0, 0, x, self.bh)), (0, 0))
            if 0 < k < 1:
                w = max(2, int(5 * self.u))
                ImageDraw.Draw(c).rectangle((x - w // 2, 0, x + w // 2, self.bh), fill=self.style.col("accent"))
        self.put(img, c, t)
        self.draw_shade(img, t)

    def draw_over(self, img, t):
        if self.lab:  # ярлыки «до» и «после» — в углах рамки, на весь кадр — в углах рабочей зоны
            k = eio(prog(t, self.t_at, self.t_at + 0.9))
            b = self.area if self.full else self.box
            m = 0 if self.full else int(24 * self.u)
            if self.lab[0] is not None:
                G.blit(img, self.lab[0], b.x1 - m - self.lab[0].width, b.y0 + m, 1 - k)
            if self.lab[1] is not None:
                G.blit(img, self.lab[1], b.x0 + m, b.y0 + m, eo(k))
        self.draw_caption(img, t)

    def _reveal(self, alpha, k):
        if k >= 1:
            return alpha
        m = Image.new("L", (self.bw, self.bh), 0)
        if k > 0:
            d = ImageDraw.Draw(m)
            if self.p.get("reveal") == "circle":
                r = k * ((self.bw ** 2 + self.bh ** 2) ** 0.5) / 2
                d.ellipse((self.bw / 2 - r, self.bh / 2 - r, self.bw / 2 + r, self.bh / 2 + r), fill=255)
            else:
                soft = int(60 * self.u)
                x = int((self.bw + soft) * k)
                d.rectangle((0, 0, x - soft, self.bh), fill=255)
                for i in range(soft):  # мягкий край шторки
                    d.line((x - soft + i, 0, x - soft + i, self.bh), fill=255 - 255 * i // soft)
            m = m.filter(ImageFilter.GaussianBlur(2 * self.u)) if self.p.get("reveal") == "circle" else m
        from PIL import ImageChops
        return ImageChops.multiply(alpha, m)
