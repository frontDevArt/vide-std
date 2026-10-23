"""status — фазы проекта и следующий шаг."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project

LOG = False  # только чтение — лог в projects/<slug>/logs/ не пишем (studio/log.py)


def add(sp):
    project_parser(sp, "status", "фазы и следующий шаг")  # выходы deliverables — фазы 4–8 по каждому (B3)


def run(a):
    from ..status import report
    report(load(resolve_project(a.project)))
    return 0
