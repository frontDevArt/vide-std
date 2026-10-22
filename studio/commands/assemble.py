"""assemble — сборка финального MP4 и субтитров."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "assemble", "сборка финала")
    q.add_argument("--allow-stale", action="store_true")


def run(a):
    from ..assemble import assemble
    assemble(load(resolve_project(a.project)), allow_stale=a.allow_stale)
    return 0
