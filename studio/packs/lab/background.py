"""Пакет lab: фон §4 (две «дышащие» подсветки, сетка, пылинки — функция глобального времени) и дрейф камеры."""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ... import gfx as G
from ... import motion as M


# ===================================================================== background §4
class LabBackground:
    """Сплошной bg + подсветки (glow_cool сверху-слева, glow_warm снизу-справа, дыхание ±4 % за 7 с),
    сетка 48 px в нижних 40 % с затуханием вверх, 34 пылинки 1–2 px плывут вверх 8–20 px/с."""

    def __init__(self, W, H, seed=7, style=None):
        self.W, self.H = W, H
        pal = (style or G.SM.active()).pal
        self.z = W / 1920 if W >= H else H / 1920
        self.lw, self.lh = max(2, W // 4), max(2, H // 4)
        ys, xs = np.mgrid[0:self.lh, 0:self.lw].astype(np.float32)
        self.xs, self.ys = (xs + 0.5) * W / self.lw, (ys + 0.5) * H / self.lh
        self.base = np.array(pal["bg"], np.float32)
        self.c1 = np.array(pal["glow_cool"], np.float32)  # §14: настроение; без него = accent / accent2
        self.c2 = np.array(pal["glow_warm"], np.float32)
        rng = np.random.default_rng(seed)
        g = np.clip(rng.normal(1.2, 0.9, (H, W)), 0, 3).astype(np.uint8)  # зерно против бандинга
        self.grain = Image.merge("RGB", [Image.fromarray(g, "L")] * 3)
        # сетка: шире кадра на 2 клетки, чтобы сдвигать (параллакс)
        cell = max(8, int(round(48 * self.z)))
        self.cell = cell
        top = int(H * 0.593)
        gw = W + 2 * cell
        grid = Image.new("RGBA", (gw, H - top), (255, 255, 255, 0))  # белые линии, видимость — альфой
        a = np.zeros((H - top, gw), np.float32)
        ramp = (np.arange(H - top, dtype=np.float32) / max(1, H - top - 1))[:, None]
        a[:, ::cell] = 1.0
        a[::cell, :] = 1.0
        a = (a * ramp * 0.065 * 255).astype(np.uint8)
        grid.putalpha(Image.fromarray(a, "L"))
        self.grid, self.gtop = grid, top
        rnd = random.Random(seed)
        self.dust = [(rnd.random() * W, rnd.random() * H, (8 + rnd.random() * 12) * self.z,
                      (0.8 + rnd.random() * 1.4) * self.z, 0.18 + rnd.random() * 0.22) for _ in range(34)]

    def _glow(self, cx, cy, r, alpha):
        d = np.sqrt((self.xs - cx) ** 2 + (self.ys - cy) ** 2) / r
        return np.clip(1 - d, 0, 1) * alpha

    def frame(self, T, glow=None):
        """glow — (cool, warm) RGB подсветок главы в этот момент (render.glow_at), иначе — из палитры."""
        W, H, z = self.W, self.H, self.z
        c1, c2 = (self.c1, self.c2) if glow is None else (np.array(glow[0], np.float32), np.array(glow[1], np.float32))
        _, dx, dy = M.camera(T)
        cx, cy = dx * 0.5 * z, dy * 0.5 * z  # фон — в 0,5× от контента
        br = 1 + 0.04 * math.sin(T * math.tau / 7)
        a1 = self._glow(380 * z + cx + 30 * z * math.sin(T / 3), 180 * z + cy, 950 * z, 0.17 * br)
        a2 = self._glow(W - 300 * z + cx, H - 140 * z + cy + 20 * z * math.cos(T / 4), 900 * z, 0.15 * (2 - br))
        img = self.base * (1 - a1[..., None]) + c1 * a1[..., None]
        img = img * (1 - a2[..., None]) + c2 * a2[..., None]
        low = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
        out = ImageChops.add(low.resize((W, H), Image.BILINEAR), self.grain).convert("RGBA")
        off = int(round(cx)) % self.cell
        out.alpha_composite(self.grid.crop((self.cell - off, 0, self.cell - off + W, self.grid.height)), (0, self.gtop))
        d = ImageDraw.Draw(out, "RGBA")
        for x, y, v, r, a in self.dust:
            yy = (y - T * v) % H
            xx = x + cx
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(214, 236, 255, int(a * 255)))
        return out


def apply_camera(layer, T):
    """Масштаб/сдвиг слоя контента вокруг центра кадра (motion.camera — от глобального времени)."""
    s, dx, dy = M.camera(T)
    W, H = layer.size
    z = W / 1920 if W >= H else H / 1920
    cx, cy = W / 2, H / 2
    a = 1 / s
    return layer.transform((W, H), Image.AFFINE, (a, 0, cx - (cx + dx * z) * a, 0, a, cy - (cy + dy * z) * a),
                           resample=Image.BILINEAR)
