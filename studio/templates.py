"""Библиотека шаблонов сцен. Каждый шаблон синхронизируется с речью через биты (beats).

Контракт шаблона (чтобы Claude мог дописывать свои в projects/<slug>/templates/*.py):
    @template("name", doc="...", params={...}, beats="как используются биты")
    class X(Template):
        def setup(self): ...            # один раз: спрайты, кэши (дорогое — только здесь)
        def draw(self, img, t, T): ...  # каждый кадр: t — время сцены, T — глобальное
        def feed_speed(self, t): ...    # (опц.) скорость ленты px/s -> непрерывность между сценами
Полезное: self.bt(i) / self.be(i) — начало/конец бита i; self.D — длительность сцены;
self.io(t) — альфа плавного входа/выхода; self.u — масштаб (1.0 при 1080 по короткой стороне).
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw

from . import gfx as G
from .gfx import PAL, blit, blitc, clamp, col, eio, eo, eob, lerp, prog

REGISTRY = {}


def template(name, doc="", params=None, beats=""):
    def deco(cls):
        cls.NAME, cls.DOC, cls.PARAMS, cls.BEATS = name, doc, params or {}, beats
        REGISTRY[name] = cls
        return cls
    return deco


class Template:
    uses_phone = False

    def __init__(self, ctx, scene, state):
        self.ctx, self.s, self.state = ctx, scene, state
        self.p = scene.get("params") or {}
        self.W, self.H = ctx["W"], ctx["H"]
        self.u = min(self.W, self.H) / 1080
        self.vert = self.H >= self.W
        self.D = scene["dur"]
        self.fps = ctx["fps"]
        self.beats = scene["beats"]
        self.first, self.last = scene.get("first", False), scene.get("last", False)
        if self.vert:
            self.fx, self.fy = self.W / 2, self.H * 0.42
        else:
            self.fx, self.fy = self.W * 0.66, self.H * 0.44
        self.cy = self.H * (0.42 if self.vert else 0.47)  # центр текстовых шаблонов
        self.k = 1.0 if self.vert else 1.18               # в широком кадре текст крупнее

    # --- beats
    def bt(self, i, default=None):
        if i is None:
            return default
        if -len(self.beats) <= i < len(self.beats):
            return self.beats[i]["t0"]
        return default if default is not None else self.D

    def be(self, i, default=None):
        if -len(self.beats) <= i < len(self.beats):
            return self.beats[i]["t1"]
        return default if default is not None else self.D

    def io(self, t, a=0.35, b=0.35, enter=True, exit=True):
        k = 1.0
        if enter:
            k = min(k, eo(prog(t, 0, a)))
        if exit:
            k = min(k, 1 - prog(t, self.D - b, self.D))
        return k

    def setup(self):
        pass

    def draw(self, img, t, T):
        raise NotImplementedError

    feed_speed = None
    dim_out = 0.0  # затемнение экрана телефона в конце сцены (передаётся следующей сцене)

    def dim(self, t, target, dur=0.6, start=0.0):
        """Плавно ведём затемнение от уровня предыдущей сцены к target -> на стыке нет вспышки."""
        d0 = self.state.get("screen_dim", 0.0)
        return lerp(d0, target, eio(prog(t, start, start + dur)))


def plural(n, forms):
    if isinstance(forms, str):
        return forms
    n = abs(int(n)) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


# ============================================================== shared phone feed
class FeedStrip:
    """Длинная заранее отрисованная лента постов -> кадр = вырезка (быстро) + motion blur."""

    def __init__(self, phone, seed=3):
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
            ca, cb = np.array(PAL[c1], np.float32) * 0.55, np.array(PAL[c2], np.float32) * 0.35
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
        d.text((m, int(sh * 0.055)), "Лента", font=f, fill=col("text"))
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
    key = (ctx["W"], ctx["H"])
    if key not in _PHONES:
        ph = G.Phone(ctx["W"], ctx["H"])
        if ctx["H"] < ctx["W"]:
            ph.cx = ctx["W"] * 0.30
        _PHONES[key] = (ph, FeedStrip(ph))
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


# ============================================================== phone_lock
@template("phone_lock", doc="Экран блокировки: уведомление прилетает, часы скачком перепрыгивают вперёд. "
                            "В конце экран «разблокируется» вверх и под ним уже лента.",
          params={"time_from": "21:04", "time_to": "22:04", "date": "вторник, 20 октября",
                  "notif_app": "Лента", "notif_title": "Новое видео для тебя", "notif_text": "Посмотри, пока не удалили 👀",
                  "badge": "+1 час", "jump_beat": 1, "time": "22:04"},
          beats="бит 0 — уведомление (тап в конце бита), бит jump_beat — скачок часов")
class PhoneLock(PhoneTemplate):
    def setup(self):
        super().setup()
        ph = self.phone
        sw, sh = ph.sw, ph.sh
        wall = Image.new("RGBA", (sw, sh), (14, 11, 34, 255))
        for c, x, y, s in (("violet", .2, .25, 1.3), ("magenta", .85, .7, 1.1), ("cyan", .3, .95, 0.9)):
            spr = G.radial(int(sw * s), c, 0.5)
            blit(wall, spr, sw * x - spr.width / 2, sh * y - spr.height / 2)
        self.wall = wall
        self.f_clock = int(sw * 0.24)
        self.t_from = G.text_sprite(self.p.get("time_from", "21:04"), self.f_clock, "black", "text", glow=int(sw * .03), glow_color="violet")
        self.t_to = G.text_sprite(self.p.get("time_to", "22:04"), self.f_clock, "black", "text", glow=int(sw * .035), glow_color="magenta")
        self.t_to_c = G.text_sprite(self.p.get("time_to", "22:04"), self.f_clock, "black", "cyan")
        self.t_to_m = G.text_sprite(self.p.get("time_to", "22:04"), self.f_clock, "black", "magenta")
        self.date = G.text_sprite(self.p.get("date", ""), int(sw * 0.05), "medium", "dim")
        nw, nh = int(sw * 0.9), int(sw * 0.3)
        n = G.panel(nw, nh, int(nh * 0.22), border="cyan", glow=int(sw * 0.03), bw=2, fill_alpha=225)
        pad = (n.width - nw) // 2
        ic = G.icon("bell", int(nh * 0.42), "cyan")
        n.alpha_composite(ic, (pad + int(nh * 0.12), pad + nh // 2 - ic.height // 2))
        x0 = pad + int(nh * 0.12) + ic.width + int(nh * 0.02)
        for txt, sz, wt, c, y in ((self.p.get("notif_app", "Лента").upper(), .11, "bold", "cyan", .13),
                                  (self.p.get("notif_title", ""), .16, "bold", "text", .36),
                                  (self.p.get("notif_text", ""), .13, "medium", "dim", .62)):
            sp = G.text_sprite(txt, int(nh * sz), wt, c, align="left")
            n.alpha_composite(sp, (x0, pad + int(nh * y)))
        self.notif = n
        badge = G.text_sprite(self.p.get("badge", "+1 час"), int(sw * 0.075), "black", "amber", glow=int(sw * .025), glow_color="amber")
        self.badge = badge
        self.tj = self.bt(int(self.p.get("jump_beat", 1)), self.D * 0.5)
        self.tn = max(0.25, self.bt(0, 0.4) - 0.05)
        self.ttap = min(self.be(0, 1.6) - 0.1, self.tj - 0.3)

    def feed_speed(self, t):
        return 0.0

    def draw(self, img, t, T):
        ph = self.phone
        sw, sh = ph.sw, ph.sh
        scr = self.wall.copy()
        cy = sh * 0.2
        jk = prog(t, self.tj, self.tj + 0.28)
        if t < self.tj:
            blitc(scr, self.t_from, sw / 2, cy)
        elif jk < 1:  # глитч
            rnd = random.Random(int(t * 1000))
            j = (1 - jk) * sw * 0.04
            blitc(scr, self.t_to_c, sw / 2 - j + rnd.uniform(-j, j), cy + rnd.uniform(-j, j) * .4, 0.9)
            blitc(scr, self.t_to_m, sw / 2 + j + rnd.uniform(-j, j), cy + rnd.uniform(-j, j) * .4, 0.9)
            blitc(scr, self.t_to, sw / 2, cy, jk)
            band = rnd.uniform(0.1, 0.3) * sh
            sl = scr.crop((0, int(band), sw, int(band + sh * 0.04)))
            scr.alpha_composite(sl, (int(rnd.uniform(-1, 1) * j * 2) % sw, int(band)))
        else:
            blitc(scr, self.t_to, sw / 2, cy)
        blitc(scr, self.date, sw / 2, cy + self.f_clock * 0.72)
        # уведомление
        k = prog(t, self.tn, self.tn + 0.55)
        if k > 0:
            ny = lerp(-self.notif.height, sh * 0.42, eob(k, 1.3))
            tap = prog(t, self.ttap, self.ttap + 0.25)
            sc = 1 - 0.04 * math.sin(tap * math.pi)
            blitc(scr, self.notif, sw / 2, ny, 1.0, sc)
            if 0 < tap < 1:
                rip = G.radial(int(sw * (0.2 + 0.5 * tap)), "cyan", 0.8)
                blitc(scr, rip, sw * 0.62, ny, 1 - tap)
        # бейдж «+1 час»
        bk = prog(t, self.tj + 0.2, self.tj + 0.65)
        if bk > 0:
            blitc(scr, self.badge, sw * 0.5, cy - self.f_clock * 0.78, min(1, bk * 1.5), 0.6 + 0.4 * eob(bk))
        # разблокировка в конце: экран блокировки уезжает вверх, под ним лента
        uk = eio(prog(t, self.D - 0.55, self.D - 0.02))
        if uk > 0:
            under = self.feed_screen(t)
            under.alpha_composite(with_alpha_img(scr, 1 - uk * 0.6), (0, int(-uk * sh)))
            scr = under
        # телефон: вход с масштабом, тряска при скачке
        a = eo(prog(t, 0, 0.5)) if self.first else 1.0
        s = lerp(0.9, 1.0, eo(prog(t, 0, 0.7))) if self.first else 1.0
        shake = (1 - jk) * 12 * self.u * math.sin(t * 90) if 0 < jk < 1 else 0
        if t >= self.tj:  # лёгкий наезд после скачка
            s *= 1 + 0.03 * eio(prog(t, self.tj, self.D - 0.6)) * (1 - prog(t, self.D - 0.6, self.D))
        ph.draw(img, scr, s, shake, 0, a)
        if 0 < jk < 1:
            fl = G.radial(int(min(self.W, self.H) * 1.6), "magenta", 0.35)
            blitc(img, fl, ph.cx, ph.cy, (1 - jk))


def with_alpha_img(im, a):
    return G.with_alpha(im, a)


# ============================================================== phone_feed
@template("phone_feed", doc="Бесконечная лента в телефоне: свайп на каждый бит + между битами, motion blur, "
                            "счётчик просмотренных постов над телефоном.",
          params={"swipe_every": 0.75, "speed": 1.0, "counter": True, "counter_label": ["пост", "поста", "постов"], "time": "22:04",
                  "stop": False},
          beats="каждый бит — сильный свайп")
class PhoneFeed(PhoneTemplate):
    def _times(self):
        bt = [b["t0"] for b in self.beats]
        extra = _swipes(0.15, self.D - 0.2, float(self.p.get("swipe_every", 0.75)))
        times = sorted(set([round(x, 2) for x in bt] + [x for x in extra if all(abs(x - b) > 0.3 for b in bt)]))
        return times

    def feed_speed(self, t):
        if not hasattr(self, "_tm"):
            self._tm = self._times()
        amp = self.ctx["H"] * 2.1 * float(self.p.get("speed", 1.0))
        v = _impulse_speed(t, self._tm, amp, 0.3, base=self.ctx["H"] * 0.12)
        if self.p.get("stop"):
            v *= 1 - eio(prog(t, self.D * 0.6, self.D))
        return v

    def setup(self):
        super().setup()
        self._tm = self._times()
        self.forms = self.p.get("counter_label", ["пост", "поста", "постов"])
        if isinstance(self.forms, list):
            self.forms = tuple(self.forms)
        self.base_off = self.state.get("feed_offset", 0.0)

    def draw(self, img, t, T):
        ph = self.phone
        scr = self.feed_screen(t)
        dm = self.dim(t, 0.0, 0.4)
        if dm > 1:
            scr.alpha_composite(Image.new("RGBA", scr.size, (6, 5, 14, int(dm))))
        self.swipe_dot(scr, t, self._tm)
        ph.draw(img, scr)
        if self.p.get("counter", True):
            f = int(clamp(round(t * self.fps), 0, len(self.offs) - 1))
            n = int(self.offs[f] / self.feedstrip.post_h) + 1
            a = self.io(t, 0.3, 0.3, enter=True, exit=self.last)
            num = G.text_sprite(f"{n}", int(64 * self.u), "black", "cyan", glow=int(12 * self.u), glow_color="cyan")
            top = ph.cy - ph.sh / 2 - ph.bez
            y = top - 70 * self.u if self.vert else top + 40 * self.u
            x = ph.cx if self.vert else ph.cx + ph.sw * 0.75
            lbl = G.text_sprite(plural(n, self.forms), int(30 * self.u), "semibold", "dim")
            gap = 14 * self.u
            wsum = num.width * 0.62 + gap + lbl.width
            blitc(img, num, x - wsum / 2 + num.width * 0.31, y, a)
            blitc(img, lbl, x - wsum / 2 + num.width * 0.62 + gap + lbl.width / 2, y + 8 * self.u, a)


# ============================================================== cards
@template("cards", doc="Карточки с иконками сменяют друг друга в ритме речи (вылетают из телефона). "
                       "Прошлые уходят в ряд-историю сверху.",
          params={"cards": [{"icon": "laugh", "label": "Смешное видео", "color": "lime"}], "first_beat": 1,
                  "backdrop": "phone", "time": "22:04"},
          beats="карточка i появляется на бите first_beat+i (если битов меньше — равномерно)")
class Cards(PhoneTemplate):
    dim_out = 150.0

    def feed_speed(self, t):
        return self.ctx["H"] * 0.35 if self.p.get("backdrop", "phone") == "phone" else 0.0

    def setup(self):
        if self.p.get("backdrop", "phone") == "phone":
            super().setup()
        cards = self.p.get("cards") or []
        fb = int(self.p.get("first_beat", 0))
        self.times = []
        for i in range(len(cards)):
            t0 = self.bt(fb + i, None) if fb + i < len(self.beats) else None
            if t0 is None:
                t0 = lerp(0.4, self.D - 1.0, (i + 0.5) / max(1, len(cards)))
            self.times.append(max(0.05, t0 - 0.12))
        cw = int((560 if self.vert else 520) * self.u)
        ch = int(cw * 0.78)
        self.spr, self.mini = [], []
        for c in cards:
            color = c.get("color", "accent")
            p = G.panel(cw, ch, int(cw * 0.09), border=color, glow=int(22 * self.u), bw=4)
            pad = (p.width - cw) // 2
            ic = G.icon(c.get("icon", "star"), int(ch * 0.44), color)
            p.alpha_composite(ic, (p.width // 2 - ic.width // 2, pad + int(ch * 0.1)))
            lb = G.text_sprite(c.get("label", ""), int(ch * 0.13), "bold", "text", maxw=int(cw * 0.86))
            p.alpha_composite(lb, (p.width // 2 - lb.width // 2, pad + int(ch * 0.66)))
            self.spr.append(p)
            m = G.panel(int(cw * 0.3), int(cw * 0.3), int(cw * 0.06), border=color, glow=int(8 * self.u), bw=3)
            mi = G.icon(c.get("icon", "star"), int(cw * 0.17), color)
            m.alpha_composite(mi, (m.width // 2 - mi.width // 2, m.height // 2 - mi.height // 2))
            self.mini.append(m)

    def draw(self, img, t, T):
        if self.uses_phone and self.p.get("backdrop", "phone") == "phone":
            scr = self.feed_screen(t)
            dim = Image.new("RGBA", scr.size, (6, 5, 14, int(self.dim(t, self.dim_out, 0.5))))
            scr.alpha_composite(dim)
            self.phone.draw(img, scr)
        n = len(self.spr)
        if self.vert:
            row_y = self.H * 0.44 - self.H * 0.30 - 95 * self.u  # над телефоном
        else:
            row_y = self.fy - 330 * self.u
        ex = self.io(t, 0, 0.35, enter=False)
        for i in range(n):
            t0 = self.times[i]
            if t < t0:
                continue
            k = prog(t, t0, t0 + 0.5)
            nxt = self.times[i + 1] if i + 1 < n else None
            out = prog(t, nxt, nxt + 0.45) if nxt is not None else 0.0
            if out < 1:
                sc = lerp(0.25, 1.0, eob(k, 1.4)) * lerp(1, 0.3, eio(out))
                rot = lerp(-8, 0, eo(k)) + lerp(0, 6, out)
                x = lerp(self.fx, self.fx - (300 if self.vert else 260) * self.u, eio(out))
                y = lerp(self.fy + 120 * self.u, self.fy, eo(k)) + lerp(0, -220 * self.u, eio(out))
                blitc(img, self.spr[i], x, y, min(1, k * 2) * (1 - out) * ex, sc * lerp(0.92, 1, ex), rot)
            if out > 0:  # мини-иконка в ряд истории
                slot_x = self.fx + (i - (n - 1) / 2) * 190 * self.u
                blitc(img, self.mini[i], slot_x, row_y, eo(out) * ex, lerp(0.5, 1, eob(out)))
        if self.last:
            pass


# ============================================================== questions
@template("questions", doc="Лента замедляется и останавливается, экран темнеет (пауза). "
                           "Над телефоном по битам появляются вопросы-плашки.",
          params={"questions": ["Зачем я здесь?", "На сколько минут?"], "first_beat": 1, "time": "22:04",
                  "icons": ["question", "clock"]},
          beats="вопрос i появляется на бите first_beat+i")
class Questions(PhoneTemplate):
    dim_out = 185.0

    def feed_speed(self, t):
        return self.ctx["H"] * 0.6 * (1 - eio(prog(t, 0, 0.9)))

    def setup(self):
        super().setup()
        qs = self.p.get("questions") or []
        ics = self.p.get("icons") or ["question", "clock"]
        fb = int(self.p.get("first_beat", 1))
        self.qt, self.qs = [], []
        colors = ["cyan", "magenta", "amber", "lime"]
        qw = int((780 if self.vert else 700) * self.u)
        qh = int(170 * self.u)
        for i, q in enumerate(qs):
            t0 = self.bt(fb + i, None) if fb + i < len(self.beats) else lerp(0.8, self.D - 1, i / max(1, len(qs)))
            self.qt.append(max(0.1, t0 - 0.1))
            c = colors[i % len(colors)]
            p = G.panel(qw, qh, qh // 2, border=c, glow=int(24 * self.u), bw=4, fill_alpha=240)
            pad = (p.width - qw) // 2
            ic = G.icon(ics[i % len(ics)], int(qh * 0.56), c)
            p.alpha_composite(ic, (pad + int(qh * 0.24), p.height // 2 - ic.height // 2))
            tx = G.text_sprite(q, int(qh * 0.34), "black", "text", maxw=int(qw - qh * 1.3))
            p.alpha_composite(tx, (pad + int(qh * 0.24) + ic.width + int(qh * 0.08), p.height // 2 - tx.height // 2))
            self.qs.append(p)
        self.pause = G.icon("target", int(self.phone.sw * 0.3), "text", glow=True)
        bar = Image.new("RGBA", (int(self.phone.sw * 0.3), int(self.phone.sw * 0.3)), (0, 0, 0, 0))
        d = ImageDraw.Draw(bar)
        w = bar.width
        d.rounded_rectangle((w * .2, w * .12, w * .4, w * .88), w * .06, fill=col("text"))
        d.rounded_rectangle((w * .6, w * .12, w * .8, w * .88), w * .06, fill=col("text"))
        self.pause = G.glowify(bar, "violet", w * 0.12)

    def draw(self, img, t, T):
        ph = self.phone
        scr = self.feed_screen(t)
        scr.alpha_composite(Image.new("RGBA", scr.size, (5, 4, 12, int(self.dim(t, self.dim_out, 0.8, 0.6)))))
        pk = prog(t, 0.9, 1.4)
        if pk > 0:
            blitc(scr, self.pause, ph.sw / 2, ph.sh / 2, eo(pk) * (1 - prog(t, self.qt[0] if self.qt else self.D, (self.qt[0] if self.qt else self.D) + 0.4) * 0.6), lerp(0.6, 1, eob(pk)))
        ph.draw(img, scr)
        n = len(self.qs)
        for i, (q, t0) in enumerate(zip(self.qs, self.qt)):
            k = prog(t, t0, t0 + 0.5)
            if k <= 0:
                continue
            y = self.fy + (i - (n - 1) / 2) * 230 * self.u
            x = lerp(self.fx + (1 if i % 2 else -1) * 240 * self.u, self.fx, eo(k))
            breathe = 1 + 0.012 * math.sin((t - t0) * 3.2 + i)
            a = min(1, k * 1.8) * self.io(t, 0, 0.35, enter=False, exit=True)
            blitc(img, q, x, y, a, lerp(0.7, 1, eob(k)) * breathe)


# ============================================================== phone_close
@template("phone_close", doc="Приложение сворачивается в иконку на домашнем экране, телефон уходит, "
                             "появляется финальный текст (держится до конца).",
          params={"close_beat": -1, "final_text": "Твоё *время* — твой выбор", "final_sub": "", "time": "22:04",
                  "speed": 0.0},
          beats="на бите close_beat приложение сворачивается; финальный текст — после конца речи")
class PhoneClose(PhoneTemplate):
    def feed_speed(self, t):
        return self.ctx["H"] * float(self.p.get("speed", 0.0)) * (1 - prog(t, self.tc - 0.4, self.tc))

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        cb = int(self.p.get("close_beat", -1))
        self.tc = (self.bt(cb, self.D * 0.4) if self.beats else self.D * 0.4) + 0.1
        speech_end = max([l["t1"] for l in self.s["lines"]] or [self.D * 0.6])
        self.tf = speech_end + 0.15

    def setup(self):
        super().setup()
        ph = self.phone
        sw, sh = ph.sw, ph.sh
        home = Image.new("RGBA", (sw, sh), (14, 11, 34, 255))
        spr = G.radial(int(sw * 1.4), "violet", 0.45)
        blit(home, spr, sw * 0.5 - spr.width / 2, sh * 0.3 - spr.height / 2)
        cols = ["cyan", "magenta", "lime", "amber", "violet", "red", "cyan", "lime"]
        s = int(sw * 0.16)
        gapx = (sw - 4 * s) / 5
        self.slots = []
        for r in range(4):
            for c in range(4):
                x = gapx + c * (s + gapx)
                y = sh * 0.14 + r * (s * 1.55)
                ic = G.rrect((s, s), int(s * 0.26), col(cols[(r * 4 + c) % 8], 70),
                             outline=col(cols[(r * 4 + c) % 8], 160), width=2)
                home.alpha_composite(ic, (int(x), int(y)))
                self.slots.append((x + s / 2, y + s / 2))
        self.home = home
        self.icon_s = s
        self.app_icon = G.glowify(G.rrect((s, s), int(s * 0.26), col("magenta", 255)), "magenta", s * 0.2)
        ai = G.icon("play", int(s * 0.6), "text", glow=False)
        self.app_icon.alpha_composite(ai, (self.app_icon.width // 2 - ai.width // 2, self.app_icon.height // 2 - ai.height // 2))
        self.target = self.slots[9]
        self.final = G.text_sprite(self.p.get("final_text", ""), int(96 * self.u), "black", "text", accent="cyan",
                                   glow=int(26 * self.u), glow_color="violet", maxw=int(self.W * 0.82))
        self.sub = (G.text_sprite(self.p["final_sub"], int(40 * self.u), "medium", "dim", maxw=int(self.W * 0.8))
                    if self.p.get("final_sub") else None)

    def draw(self, img, t, T):
        ph = self.phone
        sw, sh = ph.sw, ph.sh
        k = eio(prog(t, self.tc, self.tc + 0.65))
        app = self.feed_screen(t)
        dm = self.dim(t, 0.0, 0.7)
        if dm > 1:
            app.alpha_composite(Image.new("RGBA", app.size, (5, 4, 12, int(dm))))
        if k <= 0:
            scr = app
        else:
            scr = self.home.copy()
            s = lerp(1.0, self.icon_s / sw, k)
            cx = lerp(sw / 2, self.target[0], k); cy = lerp(sh / 2, self.target[1], k)
            w, h = max(2, int(sw * s)), max(2, int(sh * lerp(1, self.icon_s / sh, k)))
            a2 = app.resize((w, h), Image.BILINEAR)
            a2.putalpha(G.rr_mask(w, h, int(lerp(ph.r, self.icon_s * 0.26, k))))
            blit(scr, a2, cx - w / 2, cy - h / 2, 1 - prog(t, self.tc + 0.45, self.tc + 0.7))
            ik = prog(t, self.tc + 0.45, self.tc + 0.75)
            if ik > 0:
                blitc(scr, self.app_icon, self.target[0], self.target[1], ik, lerp(0.8, 1, eob(ik)))
        # телефон уходит, когда речь закончилась
        ok = eio(prog(t, self.tf - 0.25, self.tf + 0.55))
        ph.draw(img, scr, lerp(1, 0.86, ok), 0, lerp(0, 60 * self.u, ok), 1 - ok)
        fk = prog(t, self.tf, self.tf + 0.7)
        if fk > 0:
            y = self.H * (0.42 if self.vert else 0.45)
            blitc(img, self.final, self.W / 2, y + (1 - eo(fk)) * 40 * self.u, eo(fk), lerp(0.94, 1, eo(fk)))
            if self.sub is not None:
                sk = prog(t, self.tf + 0.5, self.tf + 1.1)
                blitc(img, self.sub, self.W / 2, y + self.final.height * 0.55 + 40 * self.u, eo(sk))
            # медленно «дышащая» линия под текстом
            lw = int(self.W * 0.5 * eo(prog(t, self.tf + 0.3, self.tf + 1.2)))
            if lw > 4:
                ln = G.glowify(G.rrect((lw, int(6 * self.u)), 3, col("cyan")), "cyan", 10 * self.u)
                blitc(img, ln, self.W / 2, y + self.final.height * 0.5 + (90 if self.sub else 10) * self.u, eo(fk))


# ============================================================== generic templates
@template("title", doc="Заставка/глава: маленький надзаголовок + крупный заголовок, неоновая линия.",
          params={"kicker": "Глава 1", "title": "Заголовок с *акцентом*"},
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


@template("statement", doc="Крупная фраза по центру (*слово* — акцент), опционально иконка сверху и подпись.",
          params={"text": "Главная *мысль*", "icon": None, "color": "accent", "sub": None, "at_beat": 0},
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


@template("bullets", doc="Заголовок + список пунктов с иконками; пункт i появляется на бите first_beat+i.",
          params={"header": "Три шага", "items": [{"icon": "check", "text": "Пункт"}], "first_beat": 1},
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


@template("counter", doc="Большое число, которое «набегает» от from до to во время бита, с подписью.",
          params={"from": 0, "to": 100, "suffix": "", "label": "подпись", "at_beat": 0, "color": "amber"},
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


@template("outro", doc="Финальный текст с подписью; держится до конца ролика.",
          params={"text": "Твоё *время* — твой выбор", "sub": ""},
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


def load_project_templates(root):
    """Подхватить шаблоны проекта из projects/<slug>/templates/*.py."""
    import importlib.util
    from pathlib import Path
    d = Path(root) / "templates"
    if not d.exists():
        return
    for f in sorted(d.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"project_tpl_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
