"""qa — проверка финала."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "qa", "проверка финала")
    q.add_argument("--fast", action="store_true", help="без полного декодирования")
    add_out(q)


def run(a):
    from ..qa import run as qa_run
    ok = [qa_run(proj, fast=a.fast) for proj in each_out(load(resolve_project(a.project)), a.out)]
    return 0 if all(ok) else 1
