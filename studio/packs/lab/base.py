"""Пакет lab: база шаблонов LabTemplate — триггеры, шапка, фокус, уход, вердикт, «Нейрон», источник, перенос
героя-числа через склейку (state)."""
from __future__ import annotations

import math
import re

from PIL import ImageDraw

from ... import gfx as G
from ... import motion as M
from ..base import Template
from ..registry import P
from .elements import (C, SS, VERDICTS, _down, _minutes, _ss_canvas, clock_face, dot_glow, neuron_sprite, put,
                       stamp_sprite, txt)
from .triggers import SECONDS, _norm, word_time


# ===================================================================== base template
class LabTemplate(Template):
    """База шаблонов lab: триггеры по словам, шапка (рубрика + шаги / часы), фокус, уход, вердикт,
    «Нейрон», источник, перенос героя-числа через склейку (state)."""
    camera = True
    COMMON = {"chrome": P(None, "шапка: рубрика, шаги, часы (переносится в следующие сцены)", dict),
              "keep": P([], "что пережить склейку: [hero]"),
              "source": P(None, "плашка источника {label, text, at}", dict),
              "verdict": P(None, "штамп вердикта {verdict, sub, at}", dict),
              "neuron": P(None, "«Нейрон» {mood, text, at}", dict)}

    def __init__(self, ctx, scene, state):
        super().__init__(ctx, scene, state)
        self.z = self.W / 1920 if self.W >= self.H else self.W / 1080
        self.words = scene.get("words") or []
        self._planned = False

    # ---------- триггеры
    def _norm(self, w):
        return _norm(w)

    def at(self, spec, default=None, lead=True):
        """'66' | 'w:median' | 'word#2' | 'median of' (последовательность) | 3 (бит) | '1.5s' | 2.4 (сек)."""
        if spec is None:
            return default
        if isinstance(spec, bool):
            return default
        if isinstance(spec, int):
            t = self.bt(spec, default)
            return max(0.0, t - M.fr(M.F_LEAD)) if lead and t is not None else t
        if isinstance(spec, float):
            return spec
        m = SECONDS.fullmatch(str(spec).strip())
        if m:
            return float(m.group(1))
        t, _ = word_time(self.words, spec)
        if t is not None:
            return max(0.0, t - M.fr(M.F_LEAD)) if lead else t
        print(f"  ⚠️  {self.s.get('chapter')}/{self.s.get('id')}: слово-триггер «{spec}» не найдено в озвучке")
        return default

    def seq_times(self, items, start, key="at"):
        """Времена появления группы: по триггерам, иначе стаггер от start."""
        out = []
        for i, it in enumerate(items):
            out.append(self.at((it or {}).get(key), M.stagger(i, start)))
        return out

    # ---------- план (без спрайтов: нужен и для state_out/sfx_events)
    def plan(self):
        if self._planned:
            return
        self._planned = True
        p = self.p
        prev = self.state.get("lab_chrome") or {}
        ch = dict(prev)
        ch.update(p.get("chrome") or {})
        self.chrome, self.chrome_prev = ch, prev
        self.keep = set(p.get("keep") or [])
        self.exit_t = self.D - M.fr(M.F_EXIT) - 0.06
        v = p.get("verdict")
        self.v_t = self.at(v.get("at"), self.D * 0.6) if v else None
        n = p.get("neuron")
        if n:
            self.n_t = self.at(n.get("at"), (self.v_t + 1.1) if self.v_t is not None else self.D * 0.7)
        else:
            self.n_t = None
        src = p.get("source")
        self.src_t = self.at(src.get("at"), 0.9) if src else None
        self.plan_body()

    def plan_body(self):
        pass

    def state_out(self):
        self.plan()
        out = {"lab_chrome": self.chrome}
        if self.chrome.get("clock"):
            out["lab_clock"] = self.chrome["clock"]
        h = self.hero_out()
        out["lab_hero"] = h if (h and "hero" in self.keep) else None
        return out

    def hero_out(self):
        return None

    # ---------- звук §10
    def sfx_events(self):
        """[(t_локальное, имя)] — попы на появления (один на группу), тики счётчиков, удар вердикта."""
        self.plan()
        ev = []
        if self.src_t is not None:
            ev.append((self.src_t, "pop"))
        if self.v_t is not None:
            ev += [(self.v_t - 0.55, "riser"), (self.v_t, "thud")]
        if self.n_t is not None:
            ev.append((self.n_t, "pop"))
        return ev + self.sfx_body()

    def sfx_body(self):
        return []

    @staticmethod
    def ticks(t0, dur):
        """Мягкие тики счётчика, учащающиеся к концу."""
        out, x, step = [], t0, 0.11
        while x < t0 + dur:
            out.append((x, "tick"))
            x += step
            step = max(0.05, step * 0.86)
        return out

    # ---------- общий setup
    def setup(self):
        self.plan()
        z = self.z
        ch = self.chrome
        self.pill = self._pill(ch.get("rubric"), ch.get("number")) if ch.get("rubric") else None
        self.steps = [s.upper() for s in ch.get("steps") or []]
        self.step_spr = [(txt(s, 20 * z, "medium", "dim", "mono", 0.06), txt(s, 20 * z, "medium", "text", "mono", 0.06))
                         for s in self.steps]
        src = self.p.get("source")
        self.src = self._source(src.get("label", "SOURCE"), src.get("text", "")) if src else None
        v = self.p.get("verdict")
        if v:
            self.stamp = stamp_sprite(v.get("verdict", "MYTH").upper(), z)
            self.v_color = VERDICTS.get(v.get("verdict", "MYTH").upper(), "myth")
            self.v_sub = self._stamp_sub(v["sub"]) if v.get("sub") else None
            self.flash = G.radial(int(1400 * z), self.v_color, 0.55, 1.4)
        self.setup_body()

    def setup_body(self):
        pass

    def _pill(self, rubric, number):
        z = self.z
        t = txt(str(rubric).upper(), 24 * z, "extrabold", "text", "head", 0.08)
        n = txt(str(number), 20 * z, "medium", "dim", "mono", 0.02) if number else None
        w = int(26 * z + 12 * z + 14 * z + t.width + (14 * z + n.width if n else 0) + 26 * z)
        h = int(56 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), h * SS / 2, fill=C("bg2", 179), outline=(255, 255, 255, 26), width=SS)
        pill = _down(img, w, h)
        dot = dot_glow(12 * z)
        pill.alpha_composite(dot, (int(26 * z + 6 * z - dot.width / 2), int(h / 2 - dot.height / 2)))
        x = int(26 * z + 12 * z + 14 * z)
        pill.alpha_composite(t, (x, int((h - t.height) / 2 + 2 * z)))
        if n:
            pill.alpha_composite(n, (x + t.width + int(14 * z), int((h - n.height) / 2 + 2 * z)))
        return pill

    def _source(self, label, text):
        z = self.z
        a = txt(label.upper(), 18 * z, "medium", "accent", "mono", 0.06)
        b = txt(text, 18 * z, "medium", "dim", "mono")
        w, h = int(18 * z + a.width + 12 * z + b.width + 18 * z), int(44 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 10 * z * SS, fill=(10, 13, 20, 179), outline=(255, 255, 255, 26), width=SS)
        chip = _down(img, w, h)
        chip.alpha_composite(a, (int(18 * z), int((h - a.height) / 2)))
        chip.alpha_composite(b, (int(18 * z + a.width + 12 * z), int((h - b.height) / 2)))
        return chip

    def _stamp_sub(self, text):
        """Подпись под штампом: моно 26 px, *акцент* — циан."""
        z = self.z
        f = G.font(int(26 * z), "medium", "mono")
        parts = re.split(r"(\*[^*]+\*)", text)
        w = int(sum(f.getlength(p.strip("*")) for p in parts) + 44 * z)
        h = int(26 * z * 1.25 + 20 * z)
        img, d = _ss_canvas(w, h)
        d.rounded_rectangle((0, 0, w * SS - 1, h * SS - 1), 10 * z * SS, fill=(10, 13, 20, 219), outline=(255, 255, 255, 26), width=SS)
        box = _down(img, w, h)
        d = ImageDraw.Draw(box)
        x = 22 * z
        for p in parts:
            hl = p.startswith("*")
            p = p.strip("*")
            d.text((x, 10 * z), p, font=f, fill=C("accent" if hl else "text"))
            x += f.getlength(p)
        return box

    # ---------- helpers
    def vdim(self, t):
        """На вердикте всё, кроме штампа, гаснет до 32 %."""
        if self.v_t is None:
            return 1.0
        return M.lerp(1, 0.32, M.ease_in_out(M.prog(t, self.v_t - 0.15, 0.35)))

    def gone(self, t, name):
        """Уход элемента в конце сцены, если его не переносим (keep)."""
        if name in self.keep or self.last:
            return 0.0
        return M.ease_in(M.prog(t, self.exit_t, M.fr(M.F_EXIT)))

    def card(self, img, t, spr, x, y, start, act=0.0, dim=1.0, frm="bottom", name=None, ph=0.0, T=0.0, ring=None):
        """Появление 14 кадров (сдвиг 24 px, размытие 8→0, масштаб 0,96→1) + idle-покачивание + уход."""
        z = self.z
        k = M.ease_out_expo(M.prog(t, start, M.fr(M.F_APPEAR)))
        if k <= 0:
            return 0.0
        xo = self.gone(t, name) if name else 0.0
        a = k * (1 - xo) * dim
        dx = (1 - k) * 32 * z if frm == "right" else 0
        dy = (1 - k) * 24 * z if frm == "bottom" else 0
        dy += xo * 12 * z + M.bob(T, ph) * k * z
        put(img, spr, x + dx, y + dy, a, 0.96 + 0.04 * k, (1 - k) * 8 + xo * 4)
        if ring is not None and act > 0.01:
            spr_r, pad = ring
            put(img, spr_r, x + dx - pad, y + dy - pad, a * act * M.pulse(T, ph) / 1.1, 0.96 + 0.04 * k)
        return k

    # ---------- кадр
    def draw(self, img, t, T):
        self.draw_chrome(img, t, T)
        self.draw_body(img, t, T)
        z = self.z
        if self.src is not None:
            put(img, self.src, 96 * z, self.H - 160 * z + M.bob(T, 0.2) * z,
                M.appear(t, self.src_t, self.exit_t if "source" not in self.keep and not self.last else None)[0] * self.vdim(t))
        self.draw_verdict(img, t, T)
        self.draw_neuron(img, t, T)

    def draw_body(self, img, t, T):
        pass

    def draw_chrome(self, img, t, T):
        z = self.z
        ch, prev = self.chrome, self.chrome_prev
        same = prev.get("rubric") == ch.get("rubric") and prev.get("number") == ch.get("number")
        if self.pill is not None:
            k = 1.0 if same else M.ease_out_expo(M.prog(t, 0.2, M.fr(M.F_APPEAR)))
            put(img, self.pill, 96 * z, 96 * z + (1 - k) * 24 * z + M.bob(T, 1) * z, k)
        clock = ch.get("clock")
        if clock:
            self.draw_clock(img, t, T, clock)
        elif self.steps:
            cur = int(ch.get("step", 0))
            if self.v_t is not None and "VERDICT" in self.steps:
                cur_v = self.steps.index("VERDICT")
            else:
                cur_v = None
            pstep = int(prev.get("step", cur)) if prev.get("steps") else cur
            k_in = 1.0 if prev.get("steps") else M.ease_out_expo(M.prog(t, 0.35, M.fr(M.F_APPEAR)))
            x = self.W - 96 * z
            items = []
            for i, (off, on) in enumerate(self.step_spr):
                items.append((i, off, on))
            # справа налево: ширина = текст + кружок 10 + 10 + промежуток 28
            widths = [on.width + 20 * z for _, _, on in items]
            x0 = x - sum(widths) - 28 * z * (len(items) - 1)
            y = 112 * z + M.bob(T, 2) * z
            for (i, off, on), w in zip(items, widths):
                f_cur = M.ease_in_out(M.prog(t, 0.0, M.fr(M.F_FOCUS)))
                lit = (1 - f_cur) * (i == pstep) + f_cur * (i == cur)
                if cur_v is not None:
                    fv = M.ease_in_out(M.prog(t, self.v_t, M.fr(M.F_FOCUS)))
                    lit = lit * (1 - fv) + fv * (i == cur_v)
                cy = y + on.height / 2
                r = 5 * z
                dd = ImageDraw.Draw(img, "RGBA")
                a = int(255 * k_in)
                dd.ellipse((x0 - r, cy - r, x0 + r, cy + r), outline=C("dim", int(a * (1 - lit))), width=max(1, int(1.5 * z)))
                if lit > 0.01:
                    put(img, dot_glow(10 * z), x0, cy, lit * k_in, anchor="c")
                put(img, off, x0 + 10 * z, y, k_in * (1 - lit))
                put(img, on, x0 + 10 * z, y, k_in * lit)
                x0 += w + 28 * z

    def draw_clock(self, img, t, T, clock):
        """Часы дня §8.6: циферблат справа сверху, стрелка доезжает до времени новой главы."""
        z = self.z
        face = clock_face(z)
        m1 = _minutes(clock)
        m0 = _minutes(self.state.get("lab_clock")) if self.state.get("lab_clock") else m1
        k = M.ease_in_out(M.prog(t, 0.3, 1.2))
        mins = M.lerp(m0, m1, k) if m0 is not None and m1 is not None else 0
        cx, cy = self.W - 96 * z - face.width / 2, 96 * z + face.height / 2 + M.bob(T, 3) * z
        put(img, face, cx, cy, 1.0, anchor="c")
        d = ImageDraw.Draw(img, "RGBA")
        for ang, ln, wd in ((mins / 720 * math.tau, 0.24, 4), ((mins % 60) / 60 * math.tau, 0.34, 3)):
            r = face.width * ln
            d.line((cx, cy, cx + r * math.sin(ang), cy - r * math.cos(ang)), fill=C("text"), width=int(wd * z))
        d.ellipse((cx - 4 * z, cy - 4 * z, cx + 4 * z, cy + 4 * z), fill=C("accent"))
        hh, mm = int(mins // 60) % 24, int(mins % 60)
        lab = txt(f"{hh:02d}:{mm:02d}", 22 * z, "medium", "text", "mono")
        put(img, lab, cx - face.width / 2 - 14 * z - lab.width, cy - lab.height / 2, 1.0)

    def draw_verdict(self, img, t, T):
        if self.v_t is None or t < self.v_t - 0.2:
            return
        z = self.z
        f = M.prog(t, self.v_t - 0.05, 0.7)
        put(img, self.flash, self.W / 2, self.H * 0.44, math.sin(f * math.pi) * 0.9, anchor="c")
        k = M.spring(M.prog(t, self.v_t, M.fr(M.F_STAMP) + 0.25))
        a = min(1.0, k * 2)
        # масштаб 1,4→1, поворот к −8° (против часовой; у PIL положительный угол — против часовой)
        put(img, self.stamp, self.W / 2, self.H * 0.42, a, M.lerp(1.4, 1.0, k), rot=M.lerp(14, 8, k), anchor="c")
        if self.v_sub is not None:
            sk = M.ease_out_expo(M.prog(t, self.v_t + 0.45, M.fr(M.F_APPEAR)))
            box_h = self.stamp.height - 2 * int(40 * z * 2.5)  # без отступа свечения
            put(img, self.v_sub, self.W / 2, self.H * 0.42 + box_h / 2 + 22 * z + self.v_sub.height / 2 + (1 - sk) * 16 * z,
                sk, anchor="c")

    def draw_neuron(self, img, t, T):
        if self.n_t is None or t < self.n_t:
            return
        z = self.z
        n = self.p.get("neuron") or {}
        mood = n.get("mood", "surprised")
        k = M.spring(M.prog(t, self.n_t, 0.6))
        sur = M.ease_out_expo(M.prog(t, self.n_t + 0.1, 0.3)) * (1 - M.ease_in_out(M.prog(t, self.n_t + 1.4, 0.4)))
        blink = self.n_t + 1.0 < t < self.n_t + 1.12
        spr = neuron_sprite(mood if sur > 0.5 or mood == "facepalm" else "neutral", blink, z)
        x, y = n.get("x", 830), n.get("y", 700)
        nod = math.sin(M.prog(t, self.n_t + 0.4, 0.8) * math.tau * 2) * 8 * z if mood == "nod" else 0
        put(img, spr, x * z + 85 * z, y * z + 85 * z + M.bob(T, 4) * k * z + nod, min(1.0, k * 1.6) * (1 - self.gone(t, "neuron")),
            M.lerp(0.4, 1, k), rot=math.sin(T * 2.2) * 3 * k, anchor="c")
