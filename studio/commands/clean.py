"""clean — чистка кэшей build/ с отчётом об освобождённом месте (studio/clean.py)."""
from __future__ import annotations

import os
from pathlib import Path

from . import project_parser
from .. import workspace
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "clean", "чистка кэшей build/ (рендер, микс, финал)")
    q.add_argument("--keep-final", action="store_true", help="оставить build/final/ (MP4 и субтитры)")
    q.add_argument("--older-than", metavar="30d", help="только если проект не меняли столько (h/d/w); без проекта — все такие")
    q.add_argument("--dry-run", action="store_true", help="только отчёт, ничего не удалять")


def run(a):
    from ..clean import clean, parse_age, stale
    try:
        age = parse_age(a.older_than) if a.older_than else None
    except ValueError as e:
        raise SystemExit(str(e))
    if a.project or (Path(os.getcwd()) / "project.yaml").exists():
        roots = [resolve_project(a.project)]
    elif age is not None:
        roots = sorted(p for p in workspace.current().projects.iterdir()
                       if (p / "project.yaml").exists() and not p.name.startswith("_"))
    else:
        raise SystemExit("Укажите проект или --older-than (тогда — все проекты старше): python -m studio clean <проект>")
    total = 0
    for root in roots:
        if age is not None and not stale(root, age):
            print(f"{root.name}: менялся недавно (моложе {a.older_than}) — не трогаю")
            continue
        total += clean(load(root), keep_final=a.keep_final, dry_run=a.dry_run)
    if len(roots) > 1:
        print(f"Всего: {total / 1e6:.1f} МБ")
    return 0
