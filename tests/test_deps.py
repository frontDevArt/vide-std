"""Пины зависимостей: pyproject.toml и requirements.txt не должны разойтись."""
from studio.cli import STUDIO_ROOT, pinned_deps


def _requirements():
    lines = (STUDIO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return dict(ln.strip().split("==", 1) for ln in lines if ln.strip() and not ln.lstrip().startswith("#"))


def test_core_deps_pinned_exactly():
    assert set(pinned_deps()) == {"numpy", "Pillow", "PyYAML"}


def test_requirements_match_pyproject():
    assert _requirements() == pinned_deps()
