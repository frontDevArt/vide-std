"""templates — список шаблонов сцен и их параметров (с проектными, если проект указан)."""
from __future__ import annotations

from . import project_parser
from ..project import resolve_project

LOG = False  # только чтение — лог в projects/<slug>/logs/ не пишем (studio/log.py)


def add(sp):
    project_parser(sp, "templates", "список шаблонов")


def run(a):
    from ..packs import REGISTRY, load_project_templates
    if a.project:
        load_project_templates(resolve_project(a.project))
    for n, c in sorted(REGISTRY.templates().items()):
        al = REGISTRY.aliases(n)
        print(f"\n## {n}" + (f"  (алиас: {', '.join(al)})" if al else "") + f"\n{c.DOC}\n  биты: {c.BEATS}"
              f"\n  форматы: {', '.join(c.FORMATS)}\n  параметры:")
        for k, p in c.PARAMS.items():
            print(f"    {k}: {p!r}")
    return 0
