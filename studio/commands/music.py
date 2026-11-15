"""music — ИИ-трек под длину ролика (ElevenLabs Music, studio/musicgen.py): смета → «да» (--yes) → assets/music/."""
from __future__ import annotations

from ..project import load, resolve_project
from . import project_parser


def add(sp):
    q = project_parser(sp, "music", "ИИ-трек под длину ролика (ElevenLabs Music): смета, генерация, assets.yaml")
    q.add_argument("--yes", action="store_true", help="подтвердить платную генерацию (кредиты ElevenLabs)")


def run(a):
    from .. import musicgen as MG
    proj = load(resolve_project(a.project))
    errs = MG.issues(proj)
    if errs:
        for e in errs:
            print("  ❌", e)
        print("Опишите треки в music.generate (studio/musicgen.py) и повторите")
        return 1
    try:
        return _music(proj, MG, getattr(a, "yes", False))
    except MG.MusicUnavailable as e:
        print(f"❌ Музыка: {e}")
        return 2


def _music(proj, MG, yes):
    from .. import tts
    from ..imagegen import register  # дописать запись в assets.yaml (ручные записи и комментарии не трогает)
    jobs = MG.plan(proj)
    todo = [j for j in jobs if not j.out.exists()]
    print(f"Музыка: ElevenLabs {jobs[0].model}, {jobs[0].ms / 1000:g} с (длина ролика), без вокала; треков "
          f"{len(jobs)}, готово {len(jobs) - len(todo)}, сделать {len(todo)}")
    for j in jobs:
        state = "готов" if j.out.exists() else f"~{j.credits} кредитов"
        print(f"  {j.name:<6} {MG.DIR.as_posix()}/{j.out.name}  {state}")
    if not todo:
        _hint(proj, jobs, MG)
        return 0
    sub = tts._el_request("/user", ws=proj.ws).get("subscription") or {}
    left = None
    if isinstance(sub.get("character_limit"), int) and isinstance(sub.get("character_count"), int):
        left = sub["character_limit"] - sub["character_count"]
    need = sum(j.credits for j in todo)
    print(f"Смета: ~{need} кредитов ElevenLabs ({MG.CREDITS_PER_MIN}/мин), тариф {sub.get('tier', '?')}"
          + (f", осталось {left}" if left is not None else ""))
    if left is not None and left < need:
        print("❌ Кредитов не хватает — сократите число вариантов или дождитесь обновления тарифа")
        return 2
    if not yes:
        print("Платно: после «да» пользователя — python -m studio music <проект> --yes")
        return 0
    for j in todo:
        print(f"  {j.name}: генерация… (до нескольких минут)", flush=True)
        got = MG.compose(j, ws=proj.ws)
        register(proj, [MG.record(proj, j, got["song_id"], sub.get("tier", ""))])
        print(f"  ✅ {MG.DIR.as_posix()}/{j.out.name}")
    _hint(proj, jobs, MG)
    return 0


def _hint(proj, jobs, MG):
    print("Дальше: послушать варианты, выбрать — music.file: <путь> и music.under_lu (−15 по умолчанию), затем "
          "python -m studio assemble <проект>")
