"""Движение по channel/STYLE.md, раздел 6: тайминги (в кадрах при 30 fps), базовые анимации.

Всё — чистые функции от времени: кадр считается из t, без состояния (как в channel/style-demo.html).
Время везде в секундах; константы F_* — длительности в кадрах при 30 fps, переводятся через fr().
"""
from __future__ import annotations

import math

# прогресс и кривые — studio/anim.py (P2.6); prog здесь — ramp(t, start, dur): от start за dur секунд
from .anim import bezier as _bezier  # noqa: F401
from .anim import clamp, ease_in, ease_in_out, ease_out_expo, lerp, spring  # noqa: F401
from .anim import ramp as prog

FPS = 30

# --- тайминги STYLE §6 (кадры @30)
F_APPEAR = 14      # появление карточки
F_STAGGER = 5      # шаг стаггера группы (4–6)
F_LINE = 22        # отрисовка линии (18–27)
F_COUNT = 30       # счётчик цифры (24–36)
F_FOCUS = 9        # смена фокуса
F_EXIT = 9         # уход элемента
F_STAMP = 10       # штамп вердикта (+ пружина)
F_MORPH = 15       # переезд элемента между сценами
F_LEAD = 4         # анимация стартует за 3–5 кадров ДО слова-триггера

DIM = 0.62         # неактивные элементы: 55–70 % яркости


def fr(n):
    """кадры -> секунды"""
    return n / FPS


def bob(T, phase=0.0, period=5.0, amp=3.0):
    """Idle: покачивание по Y ±3 px с периодом 4–6 с, у каждого элемента своя фаза. T — глобальное время."""
    return math.sin(T * math.tau / period + phase) * amp


def pulse(T, phase=0.0):
    """Пульс свечения активного элемента ±10 % раз в 2 с."""
    return 1 + 0.1 * math.sin(T * math.pi + phase)


def window(t, start, end, f=0.3):
    """Плавное 0..1 «активен в [start, end)» — для фокуса."""
    if end <= start:
        return 0.0
    return ease_in_out(min(prog(t, start, f), 1 - prog(t, end - f, f)))


def appear(t, start, exit_at=None):
    """Стандартное появление 14 кадров + уход 9 кадров.
    -> (alpha, k_in, k_out): k_in — прогресс входа (ease-out-expo), k_out — ухода (ease-in)."""
    k = ease_out_expo(prog(t, start, fr(F_APPEAR)))
    x = ease_in(prog(t, exit_at, fr(F_EXIT))) if exit_at is not None else 0.0
    return k * (1 - x), k, x


def stagger(i, start, step=F_STAGGER):
    return start + fr(step) * i


def count(t, start, a, b, dur=F_COUNT):
    """Счётчик a -> b за 24–36 кадров, ease-out-expo."""
    return lerp(a, b, ease_out_expo(prog(t, start, fr(dur))))


def focus(t, start, end):
    """Смена фокуса 9 кадров: 0 — приглушён (DIM), 1 — в фокусе. -> (яркость, активность)."""
    a = window(t, start, end, fr(F_FOCUS))
    return lerp(DIM, 1.0, a), a


def line_progress(t, start, frames=F_LINE):
    return ease_in_out(prog(t, start, fr(frames)))


def running_dot(t, start, period=0.8, travel=1.2):
    """Бегущие точки: одна точка раз в period с, проход travel с. -> список (позиция 0..1, альфа)."""
    out = []
    if t < start:
        return out
    n0 = int((t - start - travel) / period) - 1
    for n in range(max(0, n0), int((t - start) / period) + 1):
        u = (t - start - n * period) / travel
        if 0 <= u <= 1:
            out.append((u, math.sin(u * math.pi)))
    return out


def camera(T):
    """Дрейф камеры как функция ГЛОБАЛЬНОГО времени: через склейку не прыгает.
    Масштаб 100–103 % (скорость ≈ 3 % за 10 с), сдвиг до 10–20 px. Фон двигается в 0,5× (параллакс)."""
    s = 1.015 + 0.015 * math.sin(T * math.tau / 26.0)
    dx = 14 * math.sin(T * math.tau / 33.0)
    dy = 8 * math.sin(T * math.tau / 29.0 + 1.0)
    return s, dx, dy
