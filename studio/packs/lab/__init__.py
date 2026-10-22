"""Пакет lab — визуальный язык канала Notes From The Mind (channel/STYLE.md, эталон channel/style-demo.html).

- background.py — фон §4 и дрейф камеры; elements.py — примитивы и фирменные элементы §8;
- triggers.py — триггеры `at`, check.py — их проверка; base.py — LabTemplate; hero.py, crowd.py, templates.py — шаблоны композиции §5.

Координаты — в «дизайн-пикселях» 1920×1080 (как в STYLE), масштаб self.z = W / 1920. Морфинг через склейку — только
через state (`lab_chrome`, `lab_hero`, `lab_clock`), как требует SCENE_SPEC.
"""
from . import background, elements, triggers, base, check, hero, crowd, templates  # noqa: F401
from .background import LabBackground, apply_camera, composite_camera  # noqa: F401
from .base import LabTemplate  # noqa: F401
from .check import trigger_errors  # noqa: F401
