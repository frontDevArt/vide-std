"""validate — проверить сценарий (логика — studio/validate.py)."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    project_parser(sp, "validate", "проверить сценарий")


def run(a):
    from ..validate import check
    proj = load(resolve_project(a.project))
    r = check(proj)
    print(f"Язык: {proj.cfg['language']}. Глав: {len(proj.chapters)}, сцен: {r.scenes}, слов: {r.words}, "
          f"оценка речи ≈ {r.est:.0f} c ({r.pace:g} слов/мин, {r.pace_src})")
    for w in r.warns:
        print("  ⚠️ ", w)
    for e in r.errs:
        print("  ❌", e)
    print("OK" if r.ok else "ЕСТЬ ОШИБКИ")
    return 0 if r.ok else 1
