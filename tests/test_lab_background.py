"""P3.2: фон lab дешевле — тот же кадр, что прежняя реализация (подсветки в 1/4, add, сетка полосой), с точностью
до 1/255: подсветки теперь в 1/8, остальное (add_modulo, сетка по линиям) — байт в байт."""
import math
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageChops, ImageDraw

from studio import motion as M
from studio import style as S
from studio.packs.lab.background import LabBackground


def _reference(bg, T, glow=None):
    """Кадр LabBackground до P3.2 (код 06191f5): поля 1/4 кадра, ImageChops.add, сетка — полоса шире кадра."""
    W, H, z, cell = bg.W, bg.H, bg.z, bg.cell
    lw, lh = max(2, W // 4), max(2, H // 4)
    ys, xs = np.mgrid[0:lh, 0:lw].astype(np.float32)
    xs, ys = (xs + 0.5) * W / lw, (ys + 0.5) * H / lh
    base = bg.base[:, 0, 0]
    c1, c2 = (bg.c1, bg.c2) if glow is None else (np.array(glow[0], np.float32), np.array(glow[1], np.float32))

    def g(cx, cy, r, alpha):
        return np.clip(1 - np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / r, 0, 1) * alpha

    _, dx, dy = M.camera(T)
    cx, cy = dx * 0.5 * z, dy * 0.5 * z
    br = 1 + 0.04 * math.sin(T * math.tau / 7)
    a1 = g(380 * z + cx + 30 * z * math.sin(T / 3), 180 * z + cy, 950 * z, 0.17 * br)
    a2 = g(W - 300 * z + cx, H - 140 * z + cy + 20 * z * math.cos(T / 4), 900 * z, 0.15 * (2 - br))
    img = base * (1 - a1[..., None]) + c1 * a1[..., None]
    img = img * (1 - a2[..., None]) + c2 * a2[..., None]
    low = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    out = ImageChops.add(low.resize((W, H), Image.BILINEAR), bg.grain).convert("RGBA")
    top = bg.gtop
    a = np.zeros((H - top, W + 2 * cell), np.float32)
    a[:, ::cell] = a[::cell, :] = 1.0
    a = (a * (np.arange(H - top, dtype=np.float32) / max(1, H - top - 1))[:, None] * 0.065 * 255).astype(np.uint8)
    grid = Image.new("RGBA", a.shape[::-1], (255, 255, 255, 0))
    grid.putalpha(Image.fromarray(a))
    off = int(round(cx)) % cell
    out.alpha_composite(grid.crop((cell - off, 0, cell - off + W, grid.height)), (0, top))
    d = ImageDraw.Draw(out, "RGBA")
    for x, y, v, r, al in bg.dust:
        yy, xx = (y - T * v) % H, x + cx
        d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(214, 236, 255, int(al * 255)))
    return out


def _diff(a, b):
    d = np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16))
    return d.max(), d.mean()


@pytest.mark.parametrize("W, H", [(1920, 1080), (1080, 1920), (1080, 1080)])  # форматы студии
@pytest.mark.parametrize("T, glow", [(0.0, None), (3.7, ((40, 200, 255), (255, 120, 40))), (13.0, None), (21.4, None)])
def test_matches_reference(W, H, T, glow):
    bg = LabBackground(W, H, style=S.Style("lab"))
    mx, mean = _diff(_reference(bg, T, glow), bg.frame(T, glow))
    assert mx <= 1 and mean <= 0.05  # округление полей 1/8 против 1/4; сетка и зерно — точно


def test_bright_background_saturates_like_add():
    """Фон у белого: фон + зерно > 255 — ветка ImageChops.add (насыщение), а не add_modulo (перенос через 0)."""
    pal = {"bg": (254, 254, 254), "glow_cool": (255, 255, 255), "glow_warm": (255, 255, 255)}
    bg = LabBackground(640, 360, style=SimpleNamespace(pal=pal))
    assert _diff(_reference(bg, 2.0), bg.frame(2.0))[0] <= 1  # перенос через 0 дал бы разницу ~250
