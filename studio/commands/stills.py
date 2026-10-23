"""stills — контрольные кадры (листы) и отчёт о безопасной зоне."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "stills", "контрольные кадры")
    q.add_argument("--chapter")
    q.add_argument("--times", help="глобальные времена через запятую")
    add_out(q)


def run(a):
    from ..render import stills
    from ..safezone import report
    times = [float(x) for x in a.times.split(",")] if a.times else None
    for proj in each_out(load(resolve_project(a.project)), a.out):
        stills(proj, a.chapter, times)
        report(proj, a.chapter)  # вёрстка: контент в полях кадра (P1.10; с ROADMAP B2 — ❌)
    return 0
