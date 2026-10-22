"""P3.1: камера только по рамке контента — тот же кадр, что affine всего слоя (apply_camera), с точностью до 1/255."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from studio.packs.lab.background import apply_camera, composite_camera


def _layer(W, H, boxes):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i, b in enumerate(boxes):
        d.rounded_rectangle(b, radius=12, fill=(40 + 50 * i, 200, 120, 90 + 60 * i), outline=(255, 255, 255, 255), width=3)
    return layer


def _bg(W, H):
    rng = np.random.default_rng(1)
    return Image.fromarray(rng.integers(0, 256, (H, W, 4), np.uint8)).convert("RGB").convert("RGBA")


def _diff(a, b):
    return np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).max()


@pytest.mark.parametrize("W, H, boxes", [
    (1920, 1080, [(700, 400, 1200, 700)]),                       # контент в центре
    (1920, 1080, [(0, 0, 300, 200), (1700, 900, 1919, 1079)]),   # у краёв: образ рамки уходит за кадр
    (1920, 1080, [(100, 100, 140, 130), (900, 120, 960, 160), (400, 700, 1500, 712)]),  # разбросано: пустые плитки
    (1080, 1920, [(100, 300, 980, 1500)]),                       # вертикаль
    (640, 360, [(5, 5, 635, 355)]),                              # почти весь кадр
])
@pytest.mark.parametrize("T", [0.0, 3.7, 6.5, 13.0, 21.4])
def test_matches_full_layer_affine(W, H, boxes, T):
    layer, bg = _layer(W, H, boxes), _bg(W, H)
    ref = bg.copy()
    ref.alpha_composite(apply_camera(layer, T))
    out = bg.copy()
    composite_camera(out, layer, T)
    assert _diff(ref, out) <= 1


def test_empty_layer_leaves_frame():
    bg = _bg(320, 180)
    out = bg.copy()
    composite_camera(out, Image.new("RGBA", bg.size, (0, 0, 0, 0)), 5.0)
    assert out.tobytes() == bg.tobytes()
