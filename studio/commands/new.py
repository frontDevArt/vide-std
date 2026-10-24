"""new — создать проект из шаблона projects/_template (в студии `--studio`, иначе в текущей)."""
from __future__ import annotations

import argparse
import json
import re
import shutil

from .. import workspace


def add(sp):
    q = sp.add_parser("new", help="создать проект из шаблона")
    q.add_argument("topic"); q.add_argument("--slug"); q.add_argument("--format", default=None,
                                                                      choices=["vertical", "horizontal", "square", "portrait"],
                                                                      help="без флага — из studio.yaml, иначе vertical")
    q.add_argument("--platform", help="площадка выхода (python -m studio platforms); формат без --format — по ней")
    q.add_argument("--duration", type=float, default=None, help="точная длительность, c (иначе — по речи)")
    q.add_argument("--lang", default=None, help="язык ролика: ru | en | ... (studio/lang.py); "
                                                "без флага — из studio.yaml, иначе ru")
    # то же, что `python -m studio --studio <id> new`; SUPPRESS — не затирать глобальный флаг
    q.add_argument("--studio", default=argparse.SUPPRESS, metavar="ID", help="студия проекта (studios/<id>/)")
    q.add_argument("--kind", default=None, help="тип ролика (python -m studio kinds); без флага — explainer")
    q.add_argument("--tts", choices=["elevenlabs", "edge", "rhvoice", "piper", "fake", "none"],
                   help="голос; без флага — первый доступный: elevenlabs (канал + ключ) → edge → rhvoice")


def slugify(s):
    tr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                  ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                   "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    s = "".join(tr.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "video"


def _has_edge():
    import importlib.util
    return importlib.util.find_spec("edge_tts") is not None or bool(shutil.which("edge-tts"))


def default_backend(lang):
    """Голос нового проекта — первый доступный по дешёвой проверке (без сети и синтеза), иначе None.
    ElevenLabs платный: только для канала (есть channel/POSITIONING.md, ролики англоязычные) и с ключом в .env."""
    if (workspace.secret("ELEVENLABS_API_KEY") and lang == "en"
            and workspace.current().is_channel()):
        return "elevenlabs"
    if _has_edge():
        return "edge"
    if (workspace.current().tools / "rhvoice" / "rhvoice").exists():
        return "rhvoice"
    return None


def run(a):
    sid = getattr(a, "studio", None)
    ws = workspace.studio(sid) if sid else workspace.current()
    with workspace.use(ws):
        return _create(a, ws)


def _create(a, ws):
    d = ws.config.get("defaults") or {}
    lang = a.lang or d.get("language") or "ru"
    fmt = a.format or d.get("format") or "vertical"
    pf = getattr(a, "platform", None)
    if pf:
        from ..platforms import get
        try:
            p = get(pf)
        except KeyError as e:
            raise SystemExit(f"--platform: {e.args[0]}")
        if a.format and a.format not in p.formats:
            raise SystemExit(f"--platform {pf}: формат {a.format} не подходит, нужен {' или '.join(p.formats)}")
        if fmt not in p.formats:
            fmt = p.formats[0]
    from .. import kinds, voices
    kid = getattr(a, "kind", None) or kinds.DEFAULT
    if kid not in kinds.KINDS:
        raise SystemExit(f"--kind: нет типа {kid} (есть: {', '.join(kinds.KINDS)})")
    k = kinds.KINDS[kid]
    vl = voices.layer(ws, lang)  # голос студии для языка (ROADMAP A3): бэкенд и темп — оттуда
    # ролик без голоса (music, slideshow, clip — ROADMAP C1): синтеза нет, правило «нет голоса — стоп» не действует
    backend = "none" if not k.voice else a.tts or vl.get("backend") or default_backend(lang)
    if backend == "none" and k.voice:
        raise SystemExit(f"--tts none: тип {kid} озвученный — нужен голос (или --kind music / slideshow)")
    duration = a.duration or (k.default_duration if k.exact else None)
    if not backend:
        backend = "rhvoice"
        print("⚠️  нет доступного голоса (ключ ElevenLabs для канала, edge_tts, RHVoice) — записан rhvoice;\n"
              "   поставьте голос (python -m studio doctor, bash tools/setup_rhvoice.sh) или укажите --tts")
    slug = a.slug or slugify(a.topic)
    dst = ws.project(slug)
    if dst.exists():
        raise SystemExit(f"Уже есть: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ws.template, dst)
    y = (dst / "project.yaml").read_text(encoding="utf-8")
    # JSON-строка — валидный YAML при любых кавычках и `: `/`#` в теме; комментарии заготовки сохраняются
    y = y.replace("topic: TODO", f"topic: {json.dumps(a.topic, ensure_ascii=False)}")
    y = y.replace("language: ru", f"language: {lang}")
    y = y.replace("format: vertical", f"format: {fmt}")
    if pf:
        y = y.replace("platform: null", f"platform: {pf}", 1)
    y = y.replace("kind: explainer ", f"kind: {kid} ", 1)
    y = y.replace("target_duration: null", f"target_duration: {duration if duration else 'null'}")
    # явно в project.yaml, а не «по умолчанию»: бэкенд входит в ключ кэша TTS и не должен зависеть от машины
    y = y.replace("  backend: rhvoice ", f"  backend: {backend} ", 1)
    if k.beat:  # склейки в долю трека (ROADMAP C3)
        y = y.replace("  # sync: beat ", "  sync: beat   ", 1)
    (dst / "project.yaml").write_text(y, encoding="utf-8")
    print(f"Создан проект: {dst} (тип: {kid}, голос: {backend})\nДальше: фаза 1 (бриф) — docs/PHASES.md"
          + (f"; поля brief: {', '.join(k.brief + k.files)}" if k.brief or k.files else "")
          + (f"\n⚠️  для типа {kid} в студии ещё нет шаблонов: {k.needs}" if k.needs else ""))
    return 0
