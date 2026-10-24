"""selftest — регресс студии офлайн (логика — studio/selftest.py)."""
from __future__ import annotations


def add(sp):
    q = sp.add_parser("selftest", help="регресс студии офлайн: gallery → voice (fake) → render → assemble → qa → golden")
    q.add_argument("--full", action="store_true", help="полная цепочка и на vertical (~2,5 мин), а не только horizontal")
    q.add_argument("--keep", action="store_true", help="не удалять рабочую папку (посмотреть qa/*.png)")
    q.add_argument("--workers", type=int)
    q.add_argument("--kinds", action="store_true", help="демо каждого типа ролика (ROADMAP C1) до QA вместо gallery")


def run(a):
    from ..selftest import run as selftest_run, run_kinds
    if a.kinds:
        return 0 if run_kinds(keep=a.keep, workers=a.workers) else 1
    return 0 if selftest_run(full=a.full, keep=a.keep, workers=a.workers) else 1
