"""deliver — версия и сдача: output/<slug>/vN/, CHANGELOG.md проекта, архив для клиента (ROADMAP D5, studio/deliver.py)."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "deliver", "сдача версии: output/<slug>/vN/ + CHANGELOG.md + архив для клиента")
    q.add_argument("--note", metavar="ТЕКСТ", help="заметка к версии (в CHANGELOG.md)")
    q.add_argument("--force", action="store_true", help="сдать, даже если QA не PASS или пакет с ошибками")
    q.add_argument("--list", action="store_true", help="сданные версии и чем каждая отличается от прошлой")
    q.add_argument("--diff", nargs=2, metavar=("vA", "vB"), help="отличия двух версий: --diff v1 v3")


def run(a):
    from .. import deliver as D
    proj = load(resolve_project(a.project))
    if a.list:
        D.listing(proj)
        return 0
    if a.diff:
        try:
            va, vb = (int(v.lower().lstrip("v")) for v in a.diff)
        except ValueError:
            raise SystemExit("--diff: номера версий, например --diff v1 v2")
        D.compare_versions(proj, va, vb)
        return 0
    return 0 if D.deliver(proj, note=a.note, force=a.force) else 1
