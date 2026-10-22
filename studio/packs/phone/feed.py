"""Пакет phone: общий телефон и лента постов (один набор спрайтов на процесс), база «телефонных» шаблонов."""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw

from ... import gfx as G
from ... import style as SM
from ...gfx import blit, clamp, col, eio, lerp, prog
from ..base import Template


# ============================================================== shared phone feed
class FeedStrip:
    """Длинная заранее отрисованная лента постов -> кадр = вырезка (быстро) + motion blur."""

    def __init__(self, phone, seed=3, title="Лента", style=None):
        self.title = title
        pal = (style or SM.active()).pal
        sw, sh = phone.sw, phone.sh
        self.sw, self.sh = sw, sh
        m = int(sw * 0.045)
        ph = int(sw * 1.18)
        gap = int(sw * 0.05)
        self.post_h = ph + gap
        rnd = random.Random(seed)
        N = 9
        L = N * self.post_h
        strip = Image.new("RGBA", (sw, L + sh), (12, 10, 26, 255))
        colors = ["cyan", "magenta", "violet", "lime", "amber", "red"]
        icons = ["play", "laugh", "star", "heart", "news", "book", "bolt", "eye"]
        posts = []
        for i in range(N):
            p = Image.new("RGBA", (sw - 2 * m, ph), (0, 0, 0, 0))
            d = ImageDraw.Draw(p)
            c1, c2 = rnd.sample(colors, 2)
            av = int(sw * 0.09)
            d.ellipse((0, 0, av, av), fill=col(c1, 255))
            d.rounded_rectangle((av + m * 0.6, av * 0.18, av + m * 0.6 + sw * rnd.uniform(.25, .4), av * 0.46),
                                av * 0.14, fill=(230, 226, 255, 200))
            d.rounded_rectangle((av + m * 0.6, av * 0.6, av + m * 0.6 + sw * 0.18, av * 0.8),
                                av * 0.1, fill=(140, 134, 180, 150))
            my, mh = int(av * 1.3), int(ph * 0.66)
            # медиа: градиент двух неоновых цветов
            gw = sw - 2 * m
            a = np.linspace(0, 1, gw, dtype=np.float32)[None, :, None]
            b = np.linspace(0, 1, mh, dtype=np.float32)[:, None, None]
            k = np.clip(0.55 * a + 0.45 * b, 0, 1)
            ca, cb = np.array(pal[c1], np.float32) * 0.55, np.array(pal[c2], np.float32) * 0.35
            g = (ca * (1 - k) + cb * k + 10).astype(np.uint8)
            media = Image.fromarray(np.broadcast_to(g, (mh, gw, 3)).copy(), "RGB").convert("RGBA")
            media.putalpha(G.rr_mask(gw, mh, int(sw * 0.05)))
            ic = G.icon(rnd.choice(icons), int(mh * 0.34), "text")
            media.alpha_composite(ic, (gw // 2 - ic.width // 2, mh // 2 - ic.height // 2))
            p.alpha_composite(media, (0, my))
            ry = my + mh + int(m * 0.7)
            for j, nm in enumerate(("heart", "news", "bolt")):
                ii = G.icon(nm, int(sw * 0.065), "dim", glow=False)
                p.alpha_composite(ii, (int(j * sw * 0.11), ry))
            for j, wd in enumerate((rnd.uniform(.6, .85), rnd.uniform(.35, .6))):
                yy = ry + sw * 0.1 + j * sw * 0.055
                d.rounded_rectangle((0, yy, gw * wd, yy + sw * 0.03), sw * 0.015, fill=(200, 196, 235, 150))
            posts.append(p)
        for i, p in enumerate(posts):
            strip.alpha_composite(p, (m, i * self.post_h + int(sh * 0.15)))
        strip.paste(strip.crop((0, 0, sw, sh)), (0, L))
        self.L = L
        self.strip = np.asarray(strip.convert("RGB"))
        # шапка приложения
        hdr = Image.new("RGBA", (sw, int(sh * 0.13)), (12, 10, 26, 245))
        d = ImageDraw.Draw(hdr)
        f = G.font(int(sw * 0.075), "black")
        d.text((m, int(sh * 0.055)), self.title, font=f, fill=col("text"))
        d.rounded_rectangle((m, hdr.height - 8, m + sw * 0.17, hdr.height - 3), 3, fill=col("magenta"))
        d.line((0, hdr.height - 1, sw, hdr.height - 1), fill=(60, 52, 100, 255), width=2)
        self.header = hdr
        self.status_font = G.font(int(sw * 0.042), "semibold")

    def screen(self, offset, speed, fps, time_text="22:04"):
        off = int(offset) % self.L
        shutter = abs(speed) / fps * 0.55
        n = int(clamp(shutter / 7, 1, 10))
        if n == 1:
            arr = self.strip[off:off + self.sh]
        else:
            acc = np.zeros((self.sh, self.sw, 3), np.uint16)
            for k in range(n):
                o = int(offset - shutter * (k / (n - 1) - 0.5)) % self.L
                acc += self.strip[o:o + self.sh]
            arr = (acc // n).astype(np.uint8)
        scr = Image.fromarray(np.ascontiguousarray(arr), "RGB").convert("RGBA")
        scr.alpha_composite(self.header)
        ImageDraw.Draw(scr).text((self.sw * 0.08, self.sh * 0.018), time_text, font=self.status_font,
                                 fill=col("text"))
        return scr


_PHONES = {}


def phone_ctx(ctx):
    """Один телефон и одна лента на процесс (дорогие спрайты строятся один раз)."""
    from ...lang import profile
    title = profile(ctx.get("language"))["ui"]["feed"]
    style = ctx.get("style") or SM.active()
    key = (ctx["W"], ctx["H"], title, style)
    if key not in _PHONES:
        ph = G.Phone(ctx["W"], ctx["H"], style=style)
        if ctx["H"] < ctx["W"]:
            ph.cx = ctx["W"] * 0.30
        _PHONES[key] = (ph, FeedStrip(ph, title=title, style=style))
    return _PHONES[key]


class PhoneTemplate(Template):
    uses_phone = True

    def setup(self):
        self.phone, self.feedstrip = phone_ctx(self.ctx)
        n = self.s["n_frames"]
        off = self.state.get("feed_offset", 0.0)
        self.offs, self.spd = [], []
        for f in range(n):
            v = self.feed_speed(f / self.fps) if self.feed_speed else 0.0
            self.offs.append(off); self.spd.append(v)
            off += v / self.fps

    def feed_screen(self, t):
        f = int(clamp(round(t * self.fps), 0, len(self.offs) - 1))
        return self.feedstrip.screen(self.offs[f], self.spd[f], self.fps, self.p.get("time", "22:04"))

    def swipe_dot(self, scr, t, times, dur=0.35):
        """Палец: светящаяся точка, проводящая вверх по экрану в моменты свайпов."""
        for ts in times:
            k = prog(t, ts, ts + dur)
            if 0 < k < 1:
                y = lerp(self.phone.sh * 0.78, self.phone.sh * 0.35, eio(k))
                a = math.sin(k * math.pi)
                dot = G.radial(int(self.phone.sw * 0.28), "text", 0.55)
                blit(scr, dot, self.phone.sw * 0.62 - dot.width / 2, y - dot.height / 2, a)


def _swipes(t0, t1, every):
    out, t = [], t0
    while t < t1:
        out.append(t); t += every
    return out


def _impulse_speed(t, times, amp, tau=0.32, base=0.0):
    v = base
    for ts in times:
        if t >= ts:
            v += amp * math.exp(-(t - ts) / tau) * min(1.0, (t - ts) / 0.06)
    return v


