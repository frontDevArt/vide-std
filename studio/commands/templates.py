"""templates — список шаблонов сцен и их параметров (с проектными, если проект указан)."""
from __future__ import annotations

from . import project_parser
from ..project import resolve_project


def add(sp):
    project_parser(sp, "templates", "список шаблонов")


def run(a):
    from ..templates import REGISTRY, load_project_templates
    if a.project:
        load_project_templates(resolve_project(a.project))
    for n, c in sorted(REGISTRY.items()):
        print(f"\n## {n}\n{c.DOC}\n  биты: {c.BEATS}\n  параметры: {c.PARAMS}")
    return 0
