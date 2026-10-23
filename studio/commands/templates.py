"""templates — список шаблонов сцен и их параметров (с проектными, если проект указан).
`--md` — справочник в Markdown, `--md --write` — обновить блок шаблонов в docs/SCENE_SPEC.md (P5.3)."""
from __future__ import annotations

from pathlib import Path

from . import project_parser
from ..project import resolve_project

LOG = False  # только чтение — лог в projects/<slug>/logs/ не пишем (studio/log.py)
SPEC = Path(__file__).resolve().parents[2] / "docs" / "SCENE_SPEC.md"


def add(sp):
    q = project_parser(sp, "templates", "список шаблонов")
    q.add_argument("--md", action="store_true", help="справочник в Markdown (только встроенные, если проект не указан)")
    q.add_argument("--write", action="store_true", help="с --md: обновить блок шаблонов в docs/SCENE_SPEC.md")


def run(a):
    from ..packs import REGISTRY, load_project_templates
    if a.write and (not a.md or a.project):
        print("❌ --write — только с --md и без проекта: в SCENE_SPEC идут встроенные шаблоны")
        return 2
    if a.project:
        load_project_templates(resolve_project(a.project))
    if a.md:
        from ..packs import reference
        md = reference.markdown(REGISTRY, project=bool(a.project))
        if not a.write:
            print(md, end="")
            return 0
        raw = SPEC.read_bytes()
        old = raw.decode("utf-8").replace("\r\n", "\n")
        new = reference.replace_block(old, md)
        if new != old:
            SPEC.write_text(new, encoding="utf-8", newline="\r\n" if b"\r\n" in raw else "\n")  # переводы строк — как были
        print(f"{'✅ обновлён' if new != old else '✅ без изменений'}: {SPEC}")
        return 0
    for n, c in sorted(REGISTRY.templates().items()):
        al = REGISTRY.aliases(n)
        print(f"\n## {n}" + (f"  (алиас: {', '.join(al)})" if al else "") + f"\n{c.DOC}\n  биты: {c.BEATS}"
              f"\n  форматы: {', '.join(c.FORMATS)}\n  параметры:")
        for k, p in c.PARAMS.items():
            print(f"    {k}: {p!r}")
    return 0
