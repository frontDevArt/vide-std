"""Общее для тестов: шрифты только из assets/fonts (кадры и ширина субтитров не зависят от системы)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "fonts" / "Manrope-VF.ttf"
for _w in ("black", "extrabold", "bold", "semibold", "medium", "regular", "light"):
    os.environ.setdefault("STUDIO_FONT_" + _w.upper(), str(FONT))


def make_gallery(dst: Path, fmt: str = "horizontal") -> Path:
    """Копия фикстуры gallery (P0.2) в dst с нужным форматом: vertical | horizontal | square."""
    import shutil
    shutil.copytree(ROOT / "tests" / "fixtures" / "gallery", dst)
    p = dst / "project.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("format: horizontal", f"format: {fmt}"), encoding="utf-8")
    return dst
