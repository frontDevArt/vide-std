"""Фон студии Paper Explained: кремовая газетная бумага кодом (numpy + Pillow, детерминированно, CC0).

Запуск из корня репозитория: python studios/paper-explained/brand/make_paper.py
Пишет brand/paper.jpg (1440×2560, 9:16; кит ставит его «cover» и в 16:9). Сид фиксирован — та же картинка всегда.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

W, H = 1440, 2560
BASE = np.array([0xF6, 0xF0, 0xE2], np.float32)  # bg кита (пипетка по референсу)
rng = np.random.default_rng(20261109)


def blur_noise(scale, sigma):
    """Низкочастотные пятна: шум маленького размера, растянутый и размытый."""
    w, h = max(2, W // scale), max(2, H // scale)
    n = Image.fromarray((rng.random((h, w)) * 255).astype(np.uint8))
    n = n.resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(sigma))
    return np.asarray(n, np.float32) / 255 - 0.5


lum = 1.0
lum = lum + blur_noise(48, 30) * 0.05      # крупные пятна бумаги
lum = lum + blur_noise(10, 3) * 0.025      # средняя «облачность»
lum = lum + (rng.random((H, W)) - 0.5) * 0.035   # зерно

# волокна: короткие тонкие штрихи чуть темнее/светлее
fib = Image.new("L", (W, H), 128)
from PIL import ImageDraw  # noqa: E402
d = ImageDraw.Draw(fib)
for _ in range(2600):
    x, y = rng.random() * W, rng.random() * H
    a = rng.random() * np.pi
    ln = 6 + rng.random() * 22
    v = 128 + int((rng.random() - 0.5) * 70)
    d.line([(x, y), (x + np.cos(a) * ln, y + np.sin(a) * ln)], fill=v, width=1)
fib = np.asarray(fib.filter(ImageFilter.GaussianBlur(0.6)), np.float32) / 255 - 0.5
lum = lum + fib * 0.05

# мягкая виньетка к краям
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
lum = lum * (1 - 0.06 * np.clip(r - 0.55, 0, None) ** 1.5)

rgb = np.clip(BASE[None, None, :] * lum[..., None], 0, 255).astype(np.uint8)
out = Path(__file__).with_name("paper.jpg")
Image.fromarray(rgb).save(out, quality=92, optimize=True)
print(out, rgb.shape)
