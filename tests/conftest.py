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


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="перезаписать tests/golden/ текущим выводом (P0.4); без флага golden только сравнивается")
