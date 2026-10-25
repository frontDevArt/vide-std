"""publish — публикация вручную: карточка загрузки и отметка «опубликовано» в published.yaml (ROADMAP E1, studio/publish.py);
--api youtube — загрузка через YouTube Data API после «да» в чате (ROADMAP E2, studio/youtube.py)."""
from __future__ import annotations

from . import add_out, each_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "publish", "публикация вручную: карточка загрузки; --done --url — отметить опубликованное; "
                                      "--api youtube — загрузить через API")
    add_out(q)
    q.add_argument("--done", action="store_true", help="человек опубликовал ролик: записать в published.yaml")
    q.add_argument("--url", metavar="ССЫЛКА", help="ссылка на ролик на площадке (с --done)")
    q.add_argument("--at", metavar="ГГГГ-ММ-ДД ЧЧ:ММ", help="время публикации (с --done; без — сейчас); "
                                                         "с --api — отложенная публикация (только private)")
    q.add_argument("--note", metavar="ТЕКСТ", help="заметка к публикации (с --done)")
    q.add_argument("--force", action="store_true", help="отметить, даже если QA не PASS или пакет с ошибками")
    q.add_argument("--list", action="store_true", help="что, где и когда опубликовано")
    q.add_argument("--api", choices=("youtube",), help="через API площадки: без --yes — карточка, с --yes — загрузка")
    q.add_argument("--yes", action="store_true", help="с --api: загрузить (только после «да» человека в чате)")
    q.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private",
                   help="с --api: видимость ролика (по умолчанию private — черновик)")
    q.add_argument("--auth", action="store_true", help="с --api: войти в аккаунт канала студии в браузере")


def run(a):
    from .. import publish as P
    proj = load(resolve_project(a.project))
    if a.list:
        P.listing(proj)
        return 0
    if a.api:
        return _api(a, proj)
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


def _api(a, proj):
    from .. import youtube as Y
    if a.auth:
        Y.auth(proj.ws)
        return 0
    if a.done or a.force:
        raise SystemExit("--api: без --done и --force — запись делает сама загрузка, ворота обязательны")
    outs = [t for t in proj.targets(a.out) if Y.supports(t)]
    if not outs:
        raise SystemExit("--api youtube: у проекта нет выхода YouTube — остальные площадки вручную (без --api)")
    if a.yes:
        if len(outs) > 1:
            raise SystemExit("--yes: одна загрузка — --out <выход> (" + ", ".join(t.out for t in outs) + ")")
        return 0 if Y.upload(outs[0], a.privacy, a.at) else 1
    bad = 0
    for t in outs:
        if len(outs) > 1:
            print(f"== выход {t.out} ==")
        bad += not Y.card(t, a.privacy, a.at)
    return 1 if bad else 0
