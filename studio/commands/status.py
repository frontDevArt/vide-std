"""status — фазы проекта и следующий шаг."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    project_parser(sp, "status", "фазы и следующий шаг")


def run(a):
    from ..status import report
    report(load(resolve_project(a.project)))
    return 0
