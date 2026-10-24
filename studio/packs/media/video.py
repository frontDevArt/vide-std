"""Пакет media: шаблоны с видео — video (кусок видео в сцене), screen (запись экрана: зум, выноски), clip (кусок
подкаста или интервью: видео/звук исходника, волна, караоке-подписи из расшифровки).

Звук исходника (`audio: true` у video и clip) идёт в микс вместо голоса (`audio_clips` → audio.media_track):
громкость итога по LUFS, музыка приглушается под ним, как под диктором."""
from __future__ import annotations

from PIL import Image, ImageDraw

from ... import gfx as G
from ... import media as MD
from ...gfx import blitc, eio, eo, lerp, prog
from ..base import Box
from ..registry import AT, NUM, P, template
from .base import MediaTemplate, ease_cos


class _VideoBase(MediaTemplate):
    """Видео (или картинка — для screen) в рамке: поток кадров `media.Video`, стоп-кадр после конца исходника."""
    VIDEO = {"file": P(None, "видео (mp4/mov/webm) или картинка, путь от папки проекта (assets/…)", str),
             "start": P(0.0, "с какой секунды исходника", NUM),
             "speed": P(1.0, "скорость: 0,5 — вдвое медленнее, 2 — вдвое быстрее (звук — тем же темпом)", NUM),
             "fit": P("cover", "cover — под обрез | contain — целиком"),
             "audio": P(False, "звук исходника — в микс (вместо голоса: клип, интервью)"),
             "volume_db": P(0.0, "громкость звука исходника, dB (итог всё равно нормализуется по LUFS)", NUM)}

    def open_media(self, w, h, mode=None):
        f = self.p.get("file")
        mode = mode or self.p.get("fit", "cover")
        self.vid = None
        if f and MD.is_video(f):
            self.vid = MD.Video(self.src(f), w, h, self.fps, float(self.p.get("start", 0)),
                                float(self.p.get("speed", 1) or 1), mode)
            self.pic = None
        else:
            self.pic = MD.fit(MD.image(self.src(f)), w, h, mode) if f else Image.new("RGBA", (w, h), (0, 0, 0, 255))

    def media_frame(self, t):
        if self.vid is None:
            return self.pic.copy()
        return self.vid.frame(int(round(t * self.fps)))

    def audio_clips(self):
        """Звук исходника в микс: [{t, file, start, dur, speed, gain_db}] (t — время сцены)."""
        f = self.p.get("file")
        if not (self.p.get("audio") and f and (MD.is_video(f) or MD.is_audio(f))):
            return []
        return [{"t": 0.0, "file": str(self.src(f)), "start": float(self.p.get("start", 0)), "dur": self.D,
                 "speed": float(self.p.get("speed", 1) or 1), "gain_db": float(self.p.get("volume_db", 0))}]


@template("video",
          doc="Кусок видео внутри сцены: обрезка (start), скорость (speed), под обрез или целиком, рамка с формой, "
              "медленный наезд. Звук исходника — по желанию (audio: true) в микс.",
          params={**_VideoBase.VIDEO,
                  "zoom": P([1.0, 1.0], "масштаб в начале и в конце сцены (медленный наезд: [1, 1.08])", list),
                  **MediaTemplate.COMMON},
          beats="видео идёт с начала сцены; подпись — с `caption_at`; после конца исходника — стоп-кадр")
class VideoScene(_VideoBase):
    def setup(self):
        z = [max(1.0, float(v)) for v in (self.p.get("zoom") or [1.0, 1.0])][:2]
        self.z0, self.z1 = z[0], z[-1]
        self.zm = max(self.z0, self.z1)
        self.open_media(round(self.bw * self.zm), round(self.bh * self.zm))
        self.setup_frame()
        self.setup_caption()

    def draw_media(self, img, t):
        fr = self.media_frame(t)
        if self.zm > 1.0 or fr.size != (self.bw, self.bh):
            z = lerp(self.z0, self.z1, ease_cos(t / self.D)) if self.D else self.z0
            ww, wh = fr.width / z, fr.height / z  # кадр подготовлен под наибольший масштаб: окно z = 1 — весь кадр
            x0, y0 = (fr.width - ww) / 2, (fr.height - wh) / 2
            fr = fr.resize((self.bw, self.bh), Image.BICUBIC, box=(x0, y0, x0 + ww, y0 + wh))
        self.put(img, fr, t)
        self.draw_shade(img, t)


@template("screen",
          doc="Запись экрана (видео или скриншот) в окне приложения: плавный зум на область по триггерам, выноски "
              "со стрелкой к точке, кольцо-подсветка клика. Для туториалов.",
          params={**_VideoBase.VIDEO,
                  "frame": P("window", "рамка: window (окно с тремя точками) | none"),
                  "title": P(None, "заголовок окна", str),
                  "zoom": P([], "зум: [{at, box: [x0, y0, x1, y1] — доли записи; нет box — назад к целому}]", list),
                  "callouts": P([], "выноски: [{at, text, x, y — точка в долях записи, until}]", list),
                  "clicks": P([], "клики: [{at, x, y}] — кольцо расходится от точки", list),
                  **MediaTemplate.COMMON},
          beats="зум, выноски и клики — по `at` (бит, секунды или слово озвучки); выноска держится до `until` "
                "или до следующей")
class ScreenScene(_VideoBase):
    BAR = 44  # высота шапки окна, дизайн-пиксели

    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        if self.full:  # запись экрана — всегда в окне внутри рабочей зоны, а не под обрез
            a = self.area
            self.full = False
            self.box = Box(a.x0 + a.w * 0.03, a.y0 + a.h * (0.06 if self.vert else 0.02), a.x1 - a.w * 0.03,
                           a.y0 + a.h * (0.62 if self.vert else 0.98))
            self.bw, self.bh = int(self.box.w), int(self.box.h)

    def setup(self):
        bar = int(self.BAR * self.u) if self.p.get("frame", "window") == "window" else 0
        self.bar = bar
        f = self.p.get("file")
        ar = None
        if f:  # окно — по пропорциям записи, вписано в рамку
            size = MD.probe(self.src(f))["size"] if MD.is_video(f) else MD.image(self.src(f)).size
            ar = size[0] / size[1] if size else None
        sw, sh = self.bw, self.bh - bar
        if ar:
            if sw / sh > ar:
                sw = int(sh * ar)
            else:
                sh = int(sw / ar)
        self.sw, self.sh = sw, sh
        cx, cy = self.box.cx, self.box.cy
        self.box = Box(round(cx - sw / 2), round(cy - (sh + bar) / 2), round(cx + sw / 2), round(cy + (sh + bar) / 2))
        self.bw, self.bh = int(self.box.w), int(self.box.h)
        self.zm = 2.5  # кадр записи — с запасом под зум до 2,5× (иначе мыло)
        self.open_media(round(sw * min(self.zm, 1.6)), round(sh * min(self.zm, 1.6)), "contain")
        self.zooms = sorted(((self.at(z.get("at"), 0.0), z.get("box")) for z in self.p.get("zoom") or []),
                            key=lambda x: x[0])
        self.calls = []
        cs = self.p.get("callouts") or []
        times = [self.at(c.get("at"), 0.3 + i) for i, c in enumerate(cs)]
        for i, c in enumerate(cs):
            end = self.at(c["until"], self.D) if c.get("until") is not None else (
                times[i + 1] if i + 1 < len(cs) else self.D)
            self.calls.append((times[i], end, float(c.get("x", 0.5)), float(c.get("y", 0.5)), self._bubble(c.get("text", ""))))
        self.clicks = [(self.at(c.get("at"), 0.0), float(c.get("x", 0.5)), float(c.get("y", 0.5)))
                       for c in self.p.get("clicks") or []]
        self.chrome = self._chrome() if bar else None
        self.p.setdefault("shape", "round")
        self.setup_frame()
        self.setup_caption()

    def _chrome(self):
        c = Image.new("RGBA", (self.bw, self.bar), self.style.col("bg_top", 255))
        d = ImageDraw.Draw(c)
        r = int(self.bar * 0.16)
        for i, colr in enumerate(((255, 95, 87), (254, 188, 46), (40, 200, 64))):
            x = int(self.bar * 0.6 + i * r * 3.2)
            d.ellipse((x - r, self.bar / 2 - r, x + r, self.bar / 2 + r), fill=colr + (255,))
        if self.p.get("title"):
            s = G.text_sprite(self.p["title"], int(self.bar * 0.42), "semibold", "dim")
            c.alpha_composite(s, ((self.bw - s.width) // 2, (self.bar - s.height) // 2))
        return c

    def _bubble(self, text):
        s = G.text_sprite(text, int(38 * self.u * (1 if self.vert else 1.1)), "bold", "ink" if "ink" in self.style.pal
                          else "bg_top", maxw=int(self.W * 0.5))
        pad = int(18 * self.u)
        b = G.rrect((s.width + 2 * pad, s.height + pad), int(16 * self.u), self.style.col("accent"))
        b.alpha_composite(s, (pad, pad // 2))
        return b

    def view(self, t):
        """Видимая область записи (доли) в момент t: переход к box зума за 0,6 с, мягко."""
        cur = (0.0, 0.0, 1.0, 1.0)
        prev, t_prev = cur, -1.0
        for at, box in self.zooms:
            tgt = tuple(box) if box else (0.0, 0.0, 1.0, 1.0)
            if t < at:
                break
            prev, cur, t_prev = cur, tgt, at
        k = eio(prog(t, t_prev, t_prev + 0.6)) if t_prev >= 0 else 1.0
        return tuple(lerp(a, b, k) for a, b in zip(prev, cur))

    def draw(self, img, t, T):
        fr = self.media_frame(t)
        v = self.view(t)
        # окно записи — квадратное в долях: пропорция экрана = пропорция записи, картинка не тянется
        vw = vh = max(1e-3, v[2] - v[0], v[3] - v[1])
        cx, cy = (v[0] + v[2]) / 2, (v[1] + v[3]) / 2
        x0 = min(max(0.0, cx - vw / 2), max(0.0, 1 - vw))
        y0 = min(max(0.0, cy - vh / 2), max(0.0, 1 - vh))
        scr = fr.resize((self.sw, self.sh), Image.BICUBIC,
                        box=(x0 * fr.width, y0 * fr.height, (x0 + vw) * fr.width, (y0 + vh) * fr.height))
        c = Image.new("RGBA", (self.bw, self.bh), self.style.col("bg_top", 255))
        if self.chrome is not None:
            c.alpha_composite(self.chrome)
        c.alpha_composite(scr, (0, self.bar))
        to_px = lambda x, y: ((x - x0) / vw * self.sw, self.bar + (y - y0) / vh * self.sh)  # noqa: E731
        d = ImageDraw.Draw(c)
        for at, x, y in self.clicks:
            k = prog(t, at, at + 0.7)
            if 0 < k < 1:
                px, py = to_px(x, y)
                r = (14 + 46 * eo(k)) * self.u
                d.ellipse((px - r, py - r, px + r, py + r), outline=self.style.col("accent", int(255 * (1 - k))),
                          width=max(2, int(5 * self.u)))
        self.put(img, c, t)
        a = self.envelope(t)[0]
        for t0, t1, x, y, b in self.calls:
            k = min(eo(prog(t, t0, t0 + 0.35)), 1 - prog(t, t1 - 0.25, t1))
            if k <= 0:
                continue
            px, py = to_px(x, y)
            px, py = self.box.x0 + px, self.box.y0 + py
            # выноска — над точкой, если есть место, иначе под ней; в пределах рабочей зоны
            up = py - b.height - 50 * self.u > self.area.y0
            by = py - 46 * self.u - b.height / 2 if up else py + 46 * self.u + b.height / 2
            bx = min(max(px, self.area.x0 + b.width / 2), self.area.x1 - b.width / 2)
            ImageDraw.Draw(img).line((px, py, bx, by + (b.height / 2 if up else -b.height / 2)),
                                     fill=self.style.col("accent", int(255 * k * a)), width=max(2, int(4 * self.u)))
            r = 9 * self.u
            ImageDraw.Draw(img).ellipse((px - r, py - r, px + r, py + r), fill=self.style.col("accent", int(255 * k * a)))
            blitc(img, b, bx, by + (1 - k) * 16 * self.u * (1 if up else -1), k * a)
        self.draw_caption(img, t)


@template("clip",
          doc="Кусок подкаста или интервью: видео исходника (или обложка к аудио) в рамке, звук исходника в микс, "
              "волна громкости, крупные караоке-подписи из расшифровки (слова загораются по времени), имя говорящего.",
          params={**_VideoBase.VIDEO,
                  "audio": P(True, "звук исходника — в микс (речь ролика)"),
                  "cover": P(None, "картинка, если исходник — только звук (wav/mp3/m4a)", str),
                  "speaker": P(None, "плашка: имя говорящего", str),
                  "role": P(None, "плашка: кто он (вторая строка)", str),
                  "captions": P([], "расшифровка: [{t: секунды сцены, text}] — фраза до следующей (или до t1); "
                                    "слова загораются равномерно по фразе", list),
                  "wave": P(True, "волна громкости звука исходника"),
                  **MediaTemplate.COMMON},
          beats="всё по времени исходника: captions[].t — секунды от начала сцены (биты не нужны: голоса нет)")
class ClipScene(_VideoBase):
    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        if self.full and not self.p.get("box"):  # клип — в рамке в верхней половине зоны: снизу волна и подписи
            a = self.area
            if self.vert:  # 9:16, 4:5: рамка во всю ширину зоны, ~ половина её высоты
                ww, hh = a.w * 0.94, min(a.h * 0.5, a.w * 0.94 * 0.9)
            else:
                hh = a.h * 0.62
                ww = min(a.w * 0.94, hh * 16 / 9)
            y0 = a.y0 + a.h * (0.04 if self.vert else 0.03)
            self.full = False
            self.box = Box(round(a.cx - ww / 2), round(y0), round(a.cx + ww / 2), round(y0 + hh))
            self.bw, self.bh = int(self.box.w), int(self.box.h)

    def setup(self):
        f = self.p.get("file")
        self.is_audio = bool(f) and not MD.is_video(f)
        if self.is_audio:
            cov = self.p.get("cover")
            self.vid = None
            self.pic = (MD.fit(MD.image(self.src(cov)), self.bw, self.bh) if cov
                        else Image.new("RGBA", (self.bw, self.bh), self.style.col("bg_top", 255)))
        else:
            self.open_media(self.bw, self.bh)
        self.p.setdefault("shape", "round")
        self.env = None
        if self.p.get("wave", True) and f:
            x = MD.audio(self.src(f), float(self.p.get("start", 0)), self.D, float(self.p.get("speed", 1) or 1))
            self.env = MD.envelope(x, self.fps, int(round(self.D * self.fps)) + 1)
        self.plate = self._plate()
        caps = [c for c in self.p.get("captions") or [] if c.get("text")]
        self.caps = []
        for i, c in enumerate(caps):
            t0 = float(c.get("t", 0))
            t1 = float(c["t1"]) if c.get("t1") is not None else (float(caps[i + 1].get("t", self.D)) if i + 1 < len(caps)
                                                                  else self.D)
            self.caps.append((t0, t1, str(c["text"]).split()))
        self.fs = int((72 if self.vert else 60) * self.u)
        self.setup_frame()
        self.setup_caption()

    def _plate(self):
        name, role = self.p.get("speaker"), self.p.get("role")
        if not name:
            return None
        a = G.text_sprite(name, int(40 * self.u), "black", "text")
        b = G.text_sprite(role, int(28 * self.u), "medium", "dim") if role else None
        pad = int(20 * self.u)
        w = max(a.width, b.width if b else 0) + 2 * pad + int(8 * self.u)
        h = a.height + (b.height if b else 0) + pad
        p = G.rrect((w, h), int(14 * self.u), self.style.col("bg_top", 225))
        p.alpha_composite(G.rrect((int(8 * self.u), h - pad), 3, self.style.col("accent")), (pad // 2, pad // 2))
        p.alpha_composite(a, (pad + int(8 * self.u), pad // 2))
        if b:
            p.alpha_composite(b, (pad + int(8 * self.u), pad // 2 + a.height))
        return p

    def _wave(self, img, t):
        if self.env is None:
            return
        n = 48 if self.vert else 64
        x0, x1 = self.box.x0, self.box.x1
        y = self.box.y1 + 90 * self.u
        f = int(t * self.fps)
        bw = (x1 - x0) / n
        d = ImageDraw.Draw(img)
        a = self.envelope(t)[0]
        for i in range(n):
            j = f - n // 2 + i  # окно волны вокруг текущего момента; прошлое ярче
            v = float(self.env[j]) if 0 <= j < len(self.env) else 0.0
            h = max(3 * self.u, v * 70 * self.u)
            c = self.style.col("accent" if j <= f else "dim", int(255 * a * (1.0 if j <= f else 0.55)))
            xm = x0 + (i + 0.5) * bw
            d.rounded_rectangle((xm - bw * 0.3, y - h, xm + bw * 0.3, y + h), radius=int(bw * 0.3), fill=c)

    def _karaoke(self, img, t):
        for t0, t1, words in self.caps:
            if not t0 - 0.02 <= t < t1:
                continue
            n_on = int(len(words) * prog(t, t0, max(t0 + 0.2, t1 - 0.25)) + 0.999)
            spr = self._kar_sprite(tuple(words), n_on)
            a = min(prog(t, t0 - 0.02, t0 + 0.08), 1 - prog(t, t1 - 0.08, t1))
            y = self.box.y1 + 90 * self.u + (110 if self.env is not None else 20) * self.u + spr.height / 2
            blitc(img, spr, self.W / 2, min(y, self.area.y1 - spr.height / 2), max(0.0, a) * self.envelope(t)[0])

    def _kar_sprite(self, words, n_on):
        key = ("clipkar", words, n_on, self.fs, self.W, self.style)
        c = _CACHE.get(key)
        if c is not None:
            return c
        f = G.font(self.fs, "black", style=self.style)
        sp = f.getlength(" ")
        maxw = self.area.w * 0.92
        lines, cur, w = [], [], 0.0
        for i, wd in enumerate(words):
            lw = f.getlength(wd)
            if cur and w + sp + lw > maxw:
                lines.append(cur)
                cur, w = [], 0.0
            cur.append((i, wd))
            w += (sp if len(cur) > 1 else 0) + lw
        if cur:
            lines.append(cur)
        lh = int(self.fs * 1.18)
        sw = max(2, int(self.fs * 0.08))
        widths = [sum(f.getlength(x) for _, x in L) + sp * (len(L) - 1) for L in lines]
        img = Image.new("RGBA", (int(max(widths) + 4 * sw), lh * len(lines) + 4 * sw), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, L in enumerate(lines):
            x = (img.width - widths[li]) / 2
            for i, wd in L:
                col = self.style.col("accent") if i == n_on - 1 else self.style.col("text", 255 if i < n_on else 110)
                d.text((x, 2 * sw + li * lh), wd, font=f, fill=col, stroke_width=sw, stroke_fill=(0, 0, 0, 220))
                x += f.getlength(wd) + sp
        _CACHE[key] = img
        if len(_CACHE) > 256:
            _CACHE.pop(next(iter(_CACHE)))
        return img

    def draw(self, img, t, T):
        self.put(img, self.media_frame(t) if self.vid is not None else self.pic.copy(), t)
        if self.plate is not None:
            k = eo(prog(t, 0.3, 0.8))
            G.blit(img, self.plate, self.box.x0 + 24 * self.u - (1 - k) * 40 * self.u,
                   self.box.y1 - self.plate.height - 24 * self.u, k * self.envelope(t)[0])
        self._wave(img, t)
        self._karaoke(img, t)
        self.draw_caption(img, t)

    def audio_clips(self):
        f = self.p.get("file")
        if not (self.p.get("audio", True) and f):
            return []
        return [{"t": 0.0, "file": str(self.src(f)), "start": float(self.p.get("start", 0)), "dur": self.D,
                 "speed": float(self.p.get("speed", 1) or 1), "gain_db": float(self.p.get("volume_db", 0))}]


_CACHE = {}
