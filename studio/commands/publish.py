"""publish — публикация вручную: карточка загрузки и отметка «опубликовано» в published.yaml (ROADMAP E1, studio/publish.py)."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "publish", "публикация вручную: карточка загрузки; --done --url — отметить опубликованное")
    add_out(q)
    q.add_argument("--done", action="store_true", help="человек опубликовал ролик: записать в published.yaml")
    q.add_argument("--url", metavar="ССЫЛКА", help="ссылка на ролик на площадке (с --done)")
    q.add_argument("--at", metavar="ГГГГ-ММ-ДД ЧЧ:ММ", help="время публикации (с --done; без — сейчас)")
    q.add_argument("--note", metavar="ТЕКСТ", help="заметка к публикации (с --done)")
    q.add_argument("--force", action="store_true", help="отметить, даже если QA не PASS или пакет с ошибками")
    q.add_argument("--list", action="store_true", help="что, где и когда опубликовано")


def run(a):
    from .. import publish as P
    proj = load(resolve_project(a.project))
    if a.list:
        P.listing(proj)
        return 0
    if a.done:
        outs = proj.targets(a.out)
        if not a.url or len(outs) > 1:
            raise SystemExit("--done: одна публикация — --url <ссылка>" + ("" if len(outs) == 1 else
                             f" и --out <выход> ({', '.join(proj.outputs)})"))
        return 0 if P.record(outs[0], a.url, at=a.at, note=a.note, force=a.force) else 1
    bad = 0
    for t in each_out(proj, a.out):
        bad += not P.card(t)
    return 1 if bad else 0
