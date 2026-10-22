"""Общее для тестов: шрифты только из assets/fonts (кадры и ширина субтитров не зависят от системы)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "Manrope-VF.ttf"
for _w in ("black", "extrabold", "bold", "semibold", "medium", "regular", "light"):
    os.environ.setdefault("STUDIO_FONT_" + _w.upper(), str(FONT))
