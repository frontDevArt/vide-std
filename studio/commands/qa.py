"""qa — проверка финала."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "qa", "проверка финала")
    q.add_argument("--fast", action="store_true", help="без полного декодирования")


def run(a):
    from ..qa import run as qa_run
    return 0 if qa_run(load(resolve_project(a.project)), fast=a.fast) else 1
