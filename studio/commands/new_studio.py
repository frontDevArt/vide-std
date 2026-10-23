"""new-studio — новая студия из заготовки studios/_template (ROADMAP A4; мастер — команда Claude `/new-studio`).

Создаёт `studios/<id>/`: `studio.yaml` (тип, языки, площадки, defaults, голоса по языкам), `brand/brand.yaml`
(заготовка кита — цвета и шрифты снимает с референса Claude, docs/BRAND.md), `CLAUDE.md` студии, для `youtube` —
`channel/POSITIONING.md`, папки `briefs/ research/ projects/ output/` и проект демо стиля `projects/<id>-style/`
со сценарием `demo/ch01.yaml` на языке студии: `python -m studio demo <id>-style` → 10–15 с на утверждение.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import shutil

from .. import workspace

TEMPLATE = workspace.ROOT / "studios" / "_template"  # заготовка — в репозитории, не в рабочей области тестов
PLATFORMS = {"youtube": ["youtube", "youtube-shorts"], "brand": ["tiktok", "instagram-reels"],
             "client": ["tiktok", "instagram-reels"]}


def add(sp):
    q = sp.add_parser("new-studio", help="новая студия studios/<id>/ (мастер — /new-studio)")
    q.add_argument("id", help="латиница, цифры и дефис: studios/<id>/")
    q.add_argument("--name", help="название студии (канал, бренд, клиент); без флага — id")
    q.add_argument("--kind", choices=workspace.KINDS, default="brand")
    q.add_argument("--lang", default="en", help="языки роликов через запятую, первый — по умолчанию: en,ru")
    q.add_argument("--platforms", help="площадки через запятую; без флага — youtube: youtube,youtube-shorts, "
                                       "иначе tiktok,instagram-reels")
    q.add_argument("--format", choices=["vertical", "horizontal", "square"],
                   help="формат по умолчанию; без флага — youtube: horizontal, иначе vertical")
    q.add_argument("--tts", choices=["elevenlabs", "edge", "rhvoice", "piper", "fake"],
                   help="голос студии; без флага — первый доступный (как у new)")
    q.add_argument("--voice", help="ID голоса для первого языка (иначе — голос языка по умолчанию; "
                                   "elevenlabs — env:ELEVENLABS_VOICE_ID из .env студии)")


def _flow(items) -> str:
    return "[" + ", ".join(items) + "]"


def _fill(text: str, subs: dict) -> str:
    for k, v in subs.items():
        text = text.replace(f"__{k}__", v)
    return text


def _voice(lang, backend, voice):
    if backend == "elevenlabs":
        return "env:ELEVENLABS_VOICE_ID"
    from ..lang import default_voice
    return voice or default_voice(lang, backend)


def run(a):
    sid = a.id
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", sid) or sid == workspace.DEFAULT:
        raise SystemExit(f"id студии: латиница в нижнем регистре, цифры, дефис (не {workspace.DEFAULT}): {sid!r}")
    dst = workspace.ROOT / "studios" / sid
    if dst.exists():
        raise SystemExit(f"Уже есть: {dst}")
    name = a.name or sid
    langs = [x.strip() for x in a.lang.split(",") if x.strip()] or ["en"]
    platforms = [x.strip() for x in a.platforms.split(",") if x.strip()] if a.platforms else PLATFORMS[a.kind]
    fmt = a.format or ("horizontal" if a.kind == "youtube" else "vertical")

    shutil.copytree(TEMPLATE, dst, ignore=shutil.ignore_patterns(".gitkeep"))
    for d in ("briefs", "research", "projects", "output", "brand/fonts"):
        (dst / d).mkdir(parents=True, exist_ok=True)
    if a.kind != "youtube":
        shutil.rmtree(dst / "channel")
    demos = dst / "demo"  # сценарии демо заготовки — в проект демо, не в студию

    q = json.dumps(name, ensure_ascii=False)
    subs = {"ID": sid, "NAME": name, "KIND": a.kind, "LANG": langs[0], "LANGS": _flow(langs),
            "PLATFORMS": _flow(platforms), "FORMAT": fmt, "SUBS": "tiktok" if fmt == "vertical" else "karaoke",
            "LANGS_TEXT": ", ".join(langs), "PLATFORMS_TEXT": ", ".join(platforms)}
    yaml_subs = dict(subs, NAME=q)  # в YAML — строкой JSON: кавычки, `: ` и `#` в названии не ломают файл

    ws = workspace.Workspace.at(dst, id=sid, tools=workspace.studio().tools)  # голоса общие
    from .new import default_backend
    voices = []
    with workspace.use(ws):  # default_backend смотрит на студию: канал (POSITIONING) + ключ → elevenlabs
        for i, lang in enumerate(langs):
            backend = a.tts or default_backend(lang) or "rhvoice"
            v = _voice(lang, backend, a.voice if i == 0 else None)
            voices.append(f"  {lang}: {{backend: {backend}" + (f", voice: {v}" if v else "") + "}")
    yaml_subs["VOICES"] = "\n".join(voices)
    (dst / "studio.yaml").write_text(_fill((dst / "studio.yaml").read_text(encoding="utf-8"), yaml_subs),
                                     encoding="utf-8")
    (dst / "brand" / "brand.yaml").write_text(
        _fill((dst / "brand" / "brand.yaml").read_text(encoding="utf-8"), yaml_subs), encoding="utf-8")
    for f in ("CLAUDE.md", "channel/POSITIONING.md"):
        if (dst / f).exists():
            (dst / f).write_text(_fill((dst / f).read_text(encoding="utf-8"), subs), encoding="utf-8")

    from .new import _create
    slug = f"{sid}-style"
    with workspace.use(ws), contextlib.redirect_stdout(io.StringIO()):  # «Дальше: фаза 1» — не про студию
        _create(argparse.Namespace(topic=f"{name} style demo", slug=slug, lang=None, format=None, duration=None,
                                   tts=None), ws)
    proj = ws.project(slug)
    y = (proj / "project.yaml").read_text(encoding="utf-8")
    (proj / "project.yaml").write_text(y.replace("title: TODO", f"title: {json.dumps(name + ' style demo', ensure_ascii=False)}", 1),
                                       encoding="utf-8")
    src = demos / f"{langs[0]}.yaml"
    if not src.exists():
        src = demos / "en.yaml"
        print(f"⚠️  заготовки демо на {langs[0]} нет — английская: перепишите текст на язык студии")
    (proj / "demo").mkdir(exist_ok=True)
    (proj / "demo" / "ch01.yaml").write_text(_fill(src.read_text(encoding="utf-8"),
                                                    dict(subs, NAME=q[1:-1])), encoding="utf-8")
    shutil.rmtree(demos)

    from .. import brand
    from .studios import check
    warns = check(ws)
    brand.load(dst / "brand")  # заготовка кита обязана грузиться
    print(f"Студия: {dst.relative_to(workspace.ROOT).as_posix()} — {name} ({a.kind}; {', '.join(langs)}; "
          f"{', '.join(platforms)}; {fmt})")
    print("    голоса: " + "; ".join(v.strip() for v in voices))
    for w in warns:
        print(f"    ⚠️  studio.yaml: {w}")
    print(f"Дальше (мастер /new-studio): brand/brand.yaml по референсу (docs/BRAND.md), CLAUDE.md студии"
          + (", channel/POSITIONING.md" if a.kind == "youtube" else "")
          + f";\n  демо стиля: {slug}/demo/ch01.yaml → python -m studio demo {slug} --no-render → "
          f"stills {slug}-demo → demo {slug} → утверждение")
    return 0
