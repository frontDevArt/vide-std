"""render — рендер сцен (кэш)."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "render", "рендер сцен")
    q.add_argument("--chapter")
    q.add_argument("--workers", type=int)
    q.add_argument("--force", action="store_true")


def run(a):
    from ..render import render
    proj = load(resolve_project(a.project))
    render(proj, a.chapter, a.workers, force=a.force)
    return 0
