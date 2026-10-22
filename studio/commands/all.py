"""all — validate → voice → render → assemble → qa одной командой."""
from __future__ import annotations

from . import project_parser, validate, voice
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "all", "voice→render→assemble→qa")
    q.add_argument("--workers", type=int)
    q.add_argument("--fast", action="store_true", help="без полного декодирования")
    q.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")


def run(a):
    for f in (validate.run, voice.run):
        if f(a):
            return 1
    from ..render import render
    proj = load(resolve_project(a.project))
    render(proj, None, a.workers)
    from ..assemble import assemble
    assemble(proj)
    from ..qa import run as qa_run
    return 0 if qa_run(proj, fast=a.fast) else 1
