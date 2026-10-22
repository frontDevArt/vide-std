"""frame — один кадр PNG по глобальному времени."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "frame", "один кадр PNG")
    q.add_argument("t", type=float); q.add_argument("--out")


def run(a):
    from ..render import frame_png
    proj = load(resolve_project(a.project))
    out = a.out or str(proj.qa_dir / f"frame_{a.t:.2f}.png")
    frame_png(proj, a.t, out)
    print(out)
    return 0
