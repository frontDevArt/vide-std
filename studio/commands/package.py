"""package — пакет к выходу: обложка, описание, чек-лист рядом с MP4 в output/<slug>/ (ROADMAP B5, studio/package.py)."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "package", "пакет к выходу: обложка, описание, чек-лист (output/<slug>/)")
    add_out(q)


def run(a):
    from ..package import build
    bad = 0
    for proj in each_out(load(resolve_project(a.project)), a.out):
        errs, _ = build(proj)
        bad += bool(errs)
    return 1 if bad else 0
