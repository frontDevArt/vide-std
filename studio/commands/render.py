"""render — рендер сцен (кэш)."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "render", "рендер сцен")
    q.add_argument("--chapter")
    q.add_argument("--workers", type=int)
    q.add_argument("--force", action="store_true")
    q.add_argument("--draft", action="store_true", help="черновик: полразмера, ultrafast, кэш build/render-draft/")
    add_out(q)


def run(a):
    from ..render import render
    for proj in each_out(load(resolve_project(a.project)), a.out):
        render(proj, a.chapter, a.workers, force=a.force, draft=a.draft)
    return 0
