"""Общее для тестов: шрифты только из assets/fonts (кадры и ширина субтитров не зависят от системы).
Фикстура и шрифты — те же, что у `python -m studio selftest` (studio/selftest.py), чтобы pytest и selftest не разошлись."""
import pytest

from studio.project import STUDIO_ROOT as ROOT
from studio.selftest import FONT, make_gallery, pin_fonts  # noqa: F401 — make_gallery берут тесты

pin_fonts()


@pytest.fixture(autouse=True)
def _root_logs(tmp_path_factory, monkeypatch):
    """Логи команд без проекта (P2.7) — во временную папку, а не в logs/ студии."""
    from studio import workspace
    with workspace.use(workspace.current(), logs=tmp_path_factory.mktemp("logs")):
        yield


@pytest.fixture(autouse=True)
def _no_real_env(monkeypatch):
    """Настоящие `.env` студии (корень и studios/<id>/) в тесты не попадают: `workspace.secret` читает файлы напрямую
    (ROADMAP A3), а в основном checkout там живой ключ ElevenLabs. `.env` во временных папках тестов читаются."""
    from pathlib import Path
    from studio import workspace
    real, orig = Path(ROOT).resolve(), workspace._parse_env

    def parse(f):
        d = Path(f).resolve().parent
        if d == real or (d.parent.name == "studios" and d.parent.parent == real):
            return {}
        return orig(f)

    monkeypatch.setattr(workspace, "_parse_env", parse)
    yield


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="перезаписать tests/golden/ текущим выводом (P0.4); без флага golden только сравнивается")
