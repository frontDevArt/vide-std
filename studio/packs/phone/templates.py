"""Пакет phone: шаблоны первого ролика — lock, feed, cards, questions, close (алиасы phone_lock, phone_feed, …)."""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw

from ... import gfx as G
from ...gfx import blit, blitc, clamp, col, eio, eo, eob, lerp, prog
from ..base import plural
from ..registry import P, template
from .feed import PhoneTemplate, _impulse_speed, _swipes


# ============================================================== phone_lock
@template("lock", aliases=("phone_lock",),
          doc="Экран блокировки: уведомление прилетает, часы скачком перепрыгивают вперёд. "
              "В конце экран «разблокируется» вверх и под ним уже лента.",
          params={"time_from": P("21:04", "часы до скачка"), "time_to": P("22:04", "часы после скачка"),
                  "date": P("вторник, 20 октября", "дата под часами"), "notif_app": P("Лента", "приложение в уведомлении"),
                  "notif_title": P("Новое видео для тебя", "заголовок уведомления"),
                  "notif_text": P("Посмотри, пока не удалили 👀", "текст уведомления"), "badge": P("+1 час", "бейдж скачка"),
                  "jump_beat": P(1, "бит скачка часов", int), "time": P("22:04", "часы в статус-баре ленты")},
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
@template("feed", aliases=("phone_feed",),
          doc="Бесконечная лента в телефоне: свайп на каждый бит + между битами, motion blur, "
              "счётчик просмотренных постов над телефоном.",
          params={"swipe_every": P(0.75, "свайп между битами, с"), "speed": P(1.0, "сила свайпа"),
                  "counter": P(True, "счётчик постов над телефоном"),
                  "counter_label": P(["пост", "поста", "постов"], "подпись счётчика: строка или формы склонения", (list, str)),
                  "time": P("22:04", "часы в статус-баре"), "stop": P(False, "лента останавливается к концу сцены")},
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
@template("cards", aliases=("cards",),
          doc="Карточки с иконками сменяют друг друга в ритме речи (вылетают из телефона). "
              "Прошлые уходят в ряд-историю сверху.",
          params={"cards": P([{"icon": "laugh", "label": "Смешное видео", "color": "lime"}], "карточки {icon, label, color}"),
                  "first_beat": P(1, "бит первой карточки", int), "backdrop": P("phone", "phone — телефон с лентой позади"),
                  "time": P("22:04", "часы в статус-баре")},
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
@template("questions", aliases=("questions",),
          doc="Лента замедляется и останавливается, экран темнеет (пауза). "
              "Над телефоном по битам появляются вопросы-плашки.",
          params={"questions": P(["Зачем я здесь?", "На сколько минут?"], "вопросы-плашки"),
                  "first_beat": P(1, "бит первого вопроса", int), "time": P("22:04", "часы в статус-баре"),
                  "icons": P(["question", "clock"], "иконки плашек по кругу")},
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
@template("close", aliases=("phone_close",),
          doc="Приложение сворачивается в иконку на домашнем экране, телефон уходит, "
              "появляется финальный текст (держится до конца).",
          params={"close_beat": P(-1, "бит, на котором приложение сворачивается", int),
                  "final_text": P("Твоё *время* — твой выбор", "финальный текст"), "final_sub": P("", "подпись"),
                  "time": P("22:04", "часы в статус-баре"), "speed": P(0.0, "скорость ленты до сворачивания")},
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
