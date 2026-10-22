"""stills — контрольные кадры (листы) и отчёт о безопасной зоне."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "stills", "контрольные кадры")
    q.add_argument("--chapter")
    q.add_argument("--times", help="глобальные времена через запятую")


def run(a):
    from ..render import stills
    proj = load(resolve_project(a.project))
    times = [float(x) for x in a.times.split(",")] if a.times else None
    stills(proj, a.chapter, times)
    from ..safezone import report
    report(proj, a.chapter)  # вёрстка: контент в полях кадра (P1.10, пока только ⚠️)
    return 0
