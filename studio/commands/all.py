"""all — validate → voice → render → assemble → qa → package одной командой."""
from __future__ import annotations

from . import add_out, each_out, project_parser, validate, voice
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "all", "voice→render→assemble→qa→package")
    q.add_argument("--workers", type=int)
    q.add_argument("--fast", action="store_true", help="без полного декодирования")
    q.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")
    add_out(q)


def run(a):
    for f in (validate.run, voice.run):
        if f(a):
            return 1
    from ..assemble import assemble
    from ..package import build as package
    from ..qa import run as qa_run
    from ..render import render
    ok = True
    for proj in each_out(load(resolve_project(a.project)), a.out):
        render(proj, None, a.workers)
        assemble(proj)
        ok = qa_run(proj, fast=a.fast) and ok
        ok = not package(proj)[0] and ok
    return 0 if ok else 1
