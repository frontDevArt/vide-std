"""doctor — проверить окружение и TTS."""
from __future__ import annotations

import shutil

from ..project import STUDIO_ROOT


def add(sp):
    q = sp.add_parser("doctor", help="проверить окружение и TTS")
    q.add_argument("--lang", default=None, help="языки через запятую (ru,en); по умолчанию все из studio/lang.py")


def pinned_deps():
    """{пакет: версия} из [project].dependencies в pyproject.toml (только точные пины `==`)."""
    import tomllib
    data = tomllib.loads((STUDIO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return dict(d.split("==", 1) for d in data["project"]["dependencies"] if "==" in d)


def pinned_mismatches():
    from importlib.metadata import PackageNotFoundError, version
    out = []
    for name, want in pinned_deps().items():
        try:
            have = version(name)
        except PackageNotFoundError:
            have = "нет"
        if have != want:
            out.append((name, want, have))
    return out


def run(a):
    ok = True
    def line(good, name, det=""):
        nonlocal ok
        ok &= good
        print(f"  {'✅' if good else '❌'} {name} {det}")
    print("Окружение студии:")
    for t in ("ffmpeg", "ffprobe"):
        line(bool(shutil.which(t)), t)
    try:
        import numpy, PIL, yaml  # noqa
        line(True, "python: numpy, Pillow, PyYAML")
        for name, want, have in pinned_mismatches():
            # другая версия Pillow/numpy = другие пиксели; не ошибка, но кэш и эталоны QA поплывут
            print(f"  ⚠️  {name} {have}, закреплена {want} -> pip install -r requirements.txt")
    except ImportError as e:
        line(False, "python-библиотеки", f"({e}) -> pip install -r requirements.txt")
    from .. import gfx
    try:
        line(True, "шрифт (кириллица + латиница)", gfx._font_file("bold"))
    except Exception as e:
        line(False, "шрифт", str(e))
    from .. import tts
    from ..lang import LANGS
    for code in (a.lang.split(",") if a.lang else LANGS):
        for be, voice in LANGS[code]["voices"].items():
            try:
                tts.probe({"backend": be, "voice": voice}, code)
                print(f"  ✅ TTS [{code}] {be} ({voice}) — синтез работает")
            except Exception as e:
                print(f"  ⬜ TTS [{code}] {be}: {str(e)[:110]}")
    import os
    from .. import workspace
    ws = workspace.current()  # --studio <id>: ключ и голос этой студии (ROADMAP A3)
    src = workspace.secret_source("ELEVENLABS_API_KEY", ws)
    if src == "нет":
        print("  ⬜ TTS ElevenLabs: ключа нет (ELEVENLABS_API_KEY в .env студии или корневом) — не проверяем")
    else:
        try:  # платный голос студии: проверяем бесплатно, без синтеза; ключ не печатается
            line(True, f"TTS ElevenLabs [{ws.id}, ключ: {src}] —",
                 tts.el_check(ws=ws) + " (бесплатная проверка, без синтеза)")
        except Exception as e:
            line(False, "TTS ElevenLabs:", str(e)[:200])
    from ..render import default_workers
    print(f"  ℹ️  ядер CPU: {os.cpu_count()}, процессов рендера по умолчанию: {default_workers()}")
    return 0 if ok else 1
