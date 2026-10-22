"""Прогресс и кривые анимации — одно место для всех пакетов (P2.6).

Две функции прогресса с разными именами (раньше обе звались `prog` с разной семантикой):
    span(t, a, b)      — 0..1 на отрезке [a, b] (конец);          прежний gfx.prog
    ramp(t, start, dur) — 0..1 за dur секунд от start (длительность); прежний motion.prog
Кривые: кубические (ease_out_cubic …, короткие имена eo/eio/eob/ei — как в gfx) и CSS cubic-bezier
по channel/STYLE.md §6 (ease_out_expo, ease_in_out, ease_in), пружина spring.
Всё — чистые функции без состояния; gfx и motion берут их отсюда, старые имена там — алиасы.
"""
from __future__ import annotations

import math


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def lerp(a, b, k):
    return a + (b - a) * k


def span(t, a, b):
    """Прогресс 0..1 между моментами a и b; при b <= a — ступенька в a."""
    return clamp((t - a) / (b - a)) if b > a else float(t >= a)


def ramp(t, start, dur):
    """Прогресс 0..1 за dur секунд от start; при dur <= 0 — ступенька в start."""
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


# ------------------------------------------------------------------ кубические
def ease_out_cubic(k):
    return 1 - (1 - k) ** 3


def ease_in_out_cubic(k):
    return 4 * k ** 3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_out_back(k, s=1.6):
    k -= 1
    return 1 + (s + 1) * k ** 3 + s * k ** 2


def ease_in_cubic(k):
    return k ** 3


eo, eio, eob, ei = ease_out_cubic, ease_in_out_cubic, ease_out_back, ease_in_cubic


# ------------------------------------------------------------------ STYLE §6
def bezier(p1x, p1y, p2x, p2y):
    """cubic-bezier(p1x, p1y, p2x, p2y) как в CSS: x -> y (Ньютон + бисекция)."""
    def bx(u):
        return 3 * p1x * u * (1 - u) ** 2 + 3 * p2x * u * u * (1 - u) + u ** 3

    def by(u):
        return 3 * p1y * u * (1 - u) ** 2 + 3 * p2y * u * u * (1 - u) + u ** 3

    def dbx(u):
        return 3 * p1x * (1 - u) ** 2 + 6 * (p2x - p1x) * u * (1 - u) + 3 * (1 - p2x) * u * u

    def f(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        u = x
        for _ in range(6):
            d = dbx(u)
            if abs(d) < 1e-6:
                break
            u -= (bx(u) - x) / d
        if not 0 <= u <= 1 or abs(bx(u) - x) > 1e-4:
            lo, hi = 0.0, 1.0
            for _ in range(30):
                u = (lo + hi) / 2
                if bx(u) < x:
                    lo = u
                else:
                    hi = u
        return by(u)
    return f


ease_out_expo = bezier(0.16, 1, 0.3, 1)     # появления (по умолчанию)
ease_in_out = bezier(0.65, 0, 0.35, 1)      # перемещения, отрисовка линий
ease_in = bezier(0.7, 0, 0.84, 0)           # уходы


def spring(x):
    """Пружина «шлепка»: перелёт ≈ 108 % около x = 0,45, дальше затухает (STYLE §6)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    return 1 - math.exp(-5.6 * x) * math.cos(x * math.pi * 2.2)
