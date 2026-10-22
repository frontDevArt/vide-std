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
    сетка 48 px в нижних 40 % с затуханием вверх, 34 пылинки 1–2 px плывут вверх 8–20 px/с.

    Цена кадра (P3.2, 1920×1080: 27 → 13 мс): подсветки — в 1/8 разрешения, каналами (3, h, w), расстояние до
    центра — из двух одномерных квадратов; один resize RGB; зерно — add_modulo (без насыщения в 3 раза дешевле add,
    а переполнения нет, пока фон + зерно ≤ 255); сетка — только по линиям: alpha_composite с альфой 0 пиксель не
    меняет, так что ~50 узких кусков дают то же, что полоса на всю ширину."""

    def __init__(self, W, H, seed=7, style=None):
        self.W, self.H = W, H
        pal = (style or G.SM.active()).pal
        self.z = W / 1920 if W >= H else H / 1920
        self.lw, self.lh = max(2, W // 8), max(2, H // 8)
        self.xs = (np.arange(self.lw, dtype=np.float32) + 0.5) * W / self.lw  # центры клеток поля подсветки
        self.ys = (np.arange(self.lh, dtype=np.float32) + 0.5) * H / self.lh
        self.base = np.array(pal["bg"], np.float32)[:, None, None]
        self.c1 = np.array(pal["glow_cool"], np.float32)  # §14: настроение; без него = accent / accent2
        self.c2 = np.array(pal["glow_warm"], np.float32)
        rng = np.random.default_rng(seed)
        g = np.clip(rng.normal(1.2, 0.9, (H, W)), 0, 3).astype(np.uint8)  # зерно против бандинга
        self.grain, self.grain_max = Image.merge("RGB", [Image.fromarray(g)] * 3), int(g.max())
        # сетка: белые линии, видимость — альфой (ramp — затухание вверх); сдвиг по x — параллакс
        cell = max(8, int(round(48 * self.z)))
        self.cell = cell
        top = int(H * 0.593)
        ramp = (np.arange(H - top, dtype=np.float32) / max(1, H - top - 1) * 0.065 * 255).astype(np.uint8)
        self.rows = [(top + r, Image.new("RGBA", (W, 1), (255, 255, 255, int(ramp[r])))) for r in range(0, H - top, cell)]
        col = ramp.copy()
        col[::cell] = 0  # пересечения уже в rows
        self.col = Image.new("RGBA", (1, H - top), (255, 255, 255, 0))
        self.col.putalpha(Image.fromarray(col[:, None]))
        self.gtop = top
        rnd = random.Random(seed)
        self.dust = [(rnd.random() * W, rnd.random() * H, (8 + rnd.random() * 12) * self.z,
                      (0.8 + rnd.random() * 1.4) * self.z, 0.18 + rnd.random() * 0.22) for _ in range(34)]

    def _glow(self, cx, cy, r, alpha):
        d2 = ((self.xs - cx) ** 2)[None, :] + ((self.ys - cy) ** 2)[:, None]
        return np.clip(1 - np.sqrt(d2) / r, 0, 1) * alpha

    def frame(self, T, glow=None):
        """glow — (cool, warm) RGB подсветок главы в этот момент (render.glow_at), иначе — из палитры."""
        W, H, z = self.W, self.H, self.z
        c1, c2 = (self.c1, self.c2) if glow is None else (np.array(glow[0], np.float32), np.array(glow[1], np.float32))
        _, dx, dy = M.camera(T)
        cx, cy = dx * 0.5 * z, dy * 0.5 * z  # фон — в 0,5× от контента
        br = 1 + 0.04 * math.sin(T * math.tau / 7)
        a1 = self._glow(380 * z + cx + 30 * z * math.sin(T / 3), 180 * z + cy, 950 * z, 0.17 * br)
        a2 = self._glow(W - 300 * z + cx, H - 140 * z + cy + 20 * z * math.cos(T / 4), 900 * z, 0.15 * (2 - br))
        img = self.base * (1 - a1) + c1[:, None, None] * a1  # (3, h, w): у numpy длинный внутренний цикл
        img = img * (1 - a2) + c2[:, None, None] * a2
        img = np.clip(img, 0, 255).astype(np.uint8)
        up = Image.fromarray(np.ascontiguousarray(img.transpose(1, 2, 0))).resize((W, H), Image.BILINEAR)
        add = ImageChops.add_modulo if int(img.max()) + self.grain_max <= 255 else ImageChops.add
        out = add(up, self.grain).convert("RGBA")
        for y, row in self.rows:
            out.alpha_composite(row, (0, y))
        for x in range(int(round(cx)) % self.cell, W, self.cell):
            out.alpha_composite(self.col, (x, self.gtop))
        d = ImageDraw.Draw(out, "RGBA")
        for x, y, v, r, a in self.dust:
            yy = (y - T * v) % H
            xx = x + cx
            d.ellipse((xx - r, yy - r, xx + r, yy + r), fill=(214, 236, 255, int(a * 255)))
        return out


def _camera_affine(size, T):
    """(a, c, f): точка кадра (x, y) берётся из слоя в (a·x + c, a·y + f) — обратное отображение для Image.AFFINE."""
    s, dx, dy = M.camera(T)
    W, H = size
    z = W / 1920 if W >= H else H / 1920
    cx, cy = W / 2, H / 2
    a = 1 / s
    return a, cx - (cx + dx * z) * a, cy - (cy + dy * z) * a


def apply_camera(layer, T):
    """Масштаб/сдвиг слоя контента вокруг центра кадра (motion.camera — от глобального времени). Весь слой —
    эталон для composite_camera (рендер зовёт её)."""
    a, c, f = _camera_affine(layer.size, T)
    return layer.transform(layer.size, Image.AFFINE, (a, 0, c, 0, a, f), resample=Image.BILINEAR)


_CELL, _TILE = 8, 32  # px: клетка маски непустого в слое; плитка кадра, которую трансформируем целиком


def composite_camera(img, layer, T):
    """img.alpha_composite(apply_camera(layer, T)) байт в байт, но affine только там, где есть контент (P3.1).

    Affine Pillow на RGBA — ~17 нс на пиксель выхода плюс две конвертации всего слоя (RGBa и обратно), а контент
    занимает 5–25 % кадра. Источник режем по getbbox с полем 2 px прозрачного; выход делим на полосы по _TILE px,
    в полосе — подряд идущие плитки, прообраз которых (±2 px на билинейный край) задевает непустую клетку маски.
    Куски выхода не пересекаются, каждый пиксель считается той же формулой, что у целого слоя."""
    box = layer.getbbox()
    if box is None:
        return img
    W, H = layer.size
    a, c, f = _camera_affine(layer.size, T)
    sx, sy = max(0, box[0] - 2), max(0, box[1] - 2)
    src = layer.crop((sx, sy, min(W, box[2] + 2), min(H, box[3] + 2)))
    c, f = c - sx, f - sy  # дальше координаты источника — в src
    occ = np.asarray(src.getchannel("A").point(lambda v: 255 if v else 0).reduce(_CELL)) > 0
    ps = np.zeros((occ.shape[0] + 1, occ.shape[1] + 1), np.int32)  # префиксные суммы: «есть ли контент в прямоугольнике»
    ps[1:, 1:] = occ.cumsum(0).cumsum(1)

    def busy(u0, v0, u1, v1):
        i0, j0 = max(0, int(v0 // _CELL)), max(0, int(u0 // _CELL))
        i1, j1 = min(occ.shape[0], math.ceil(v1 / _CELL)), min(occ.shape[1], math.ceil(u1 / _CELL))
        return i1 > i0 and j1 > j0 and ps[i1, j1] - ps[i0, j1] - ps[i1, j0] + ps[i0, j0] > 0

    # образ src в кадре: x = (u - c) / a; запас 2 px на билинейный край
    x0, y0 = max(0, math.floor(-c / a) - 2), max(0, math.floor(-f / a) - 2)
    x1, y1 = min(W, math.ceil((src.width - c) / a) + 2), min(H, math.ceil((src.height - f) / a) + 2)
    src = src.convert("RGBa")  # то же, что делает Image.transform для RGBA, но один раз на кадр
    for ty in range(y0, y1, _TILE):
        ty1 = min(y1, ty + _TILE)
        v0, v1 = a * ty + f - 2, a * ty1 + f + 2
        run = None
        for tx in range(x0, x1 + _TILE, _TILE):
            if tx < x1 and busy(a * tx + c - 2, v0, a * min(x1, tx + _TILE) + c + 2, v1):
                run = tx if run is None else run
            elif run is not None:
                rx1 = min(x1, tx)
                part = src.transform((rx1 - run, ty1 - ty), Image.AFFINE, (a, 0, a * run + c, 0, a, a * ty + f),
                                     resample=Image.BILINEAR)
                img.alpha_composite(part.convert("RGBA"), (run, ty))
                run = None
    return img
