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
                                                                      choices=["vertical", "horizontal", "square"],
                                                                      help="без флага — из studio.yaml, иначе vertical")
    q.add_argument("--duration", type=float, default=None, help="точная длительность, c (иначе — по речи)")
    q.add_argument("--lang", default=None, help="язык ролика: ru | en | ... (studio/lang.py); "
                                                "без флага — из studio.yaml, иначе ru")
    # то же, что `python -m studio --studio <id> new`; SUPPRESS — не затирать глобальный флаг
    q.add_argument("--studio", default=argparse.SUPPRESS, metavar="ID", help="студия проекта (studios/<id>/)")
    q.add_argument("--tts", choices=["elevenlabs", "edge", "rhvoice", "piper", "fake"],
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
    import os
    from .. import tts  # noqa: F401 — подхватывает .env в окружение
    if (os.environ.get("ELEVENLABS_API_KEY", "").strip() and lang == "en"
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
    backend = a.tts or default_backend(lang)
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
    y = y.replace("target_duration: null", f"target_duration: {a.duration if a.duration else 'null'}")
    # явно в project.yaml, а не «по умолчанию»: бэкенд входит в ключ кэша TTS и не должен зависеть от машины
    y = y.replace("  backend: rhvoice ", f"  backend: {backend} ", 1)
    (dst / "project.yaml").write_text(y, encoding="utf-8")
    print(f"Создан проект: {dst} (голос: {backend})\nДальше: фаза 1 (бриф) — docs/PHASES.md")
    return 0
