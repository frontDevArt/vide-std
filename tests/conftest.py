"""Общее для тестов: шрифты только из assets/fonts (кадры и ширина субтитров не зависят от системы).
Фикстура и шрифты — те же, что у `python -m studio selftest` (studio/selftest.py), чтобы pytest и selftest не разошлись."""
from studio.project import STUDIO_ROOT as ROOT
from studio.selftest import FONT, make_gallery, pin_fonts  # noqa: F401 — make_gallery берут тесты

pin_fonts()


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true",
                     help="перезаписать tests/golden/ текущим выводом (P0.4); без флага golden только сравнивается")
