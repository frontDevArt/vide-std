"""python -m studio <команда> [проект] — единая точка входа студии."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .project import STUDIO_ROOT, load, resolve_project


def cmd_doctor(a):
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
    except ImportError as e:
        line(False, "python-библиотеки", f"({e}) -> pip install -r requirements.txt")
    from . import gfx
    try:
        line(True, "шрифт (кириллица + латиница)", gfx._font_file("bold"))
    except Exception as e:
        line(False, "шрифт", str(e))
    from . import tts
    from .lang import LANGS
    for code in (a.lang.split(",") if a.lang else LANGS):
        for be, voice in LANGS[code]["voices"].items():
            try:
                tts.probe({"backend": be, "voice": voice}, code)
                print(f"  ✅ TTS [{code}] {be} ({voice}) — синтез работает")
            except Exception as e:
                print(f"  ⬜ TTS [{code}] {be}: {str(e)[:110]}")
    import os
    print(f"  ℹ️  ядер CPU: {os.cpu_count()}")
    return 0 if ok else 1


def slugify(s):
    tr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                  ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                   "u", "f", "h", "ts", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    s = "".join(tr.get(c, c) for c in s.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "video"


def cmd_new(a):
    slug = a.slug or slugify(a.topic)
    dst = STUDIO_ROOT / "projects" / slug
    if dst.exists():
        raise SystemExit(f"Уже есть: {dst}")
    shutil.copytree(STUDIO_ROOT / "projects" / "_template", dst)
    y = (dst / "project.yaml").read_text(encoding="utf-8")
    y = y.replace("topic: TODO", f"topic: {a.topic!r}".replace("'", '"'))
    y = y.replace("language: ru", f"language: {a.lang}")
    y = y.replace("format: vertical", f"format: {a.format}")
    y = y.replace("target_duration: null", f"target_duration: {a.duration if a.duration else 'null'}")
    (dst / "project.yaml").write_text(y, encoding="utf-8")
    print(f"Создан проект: {dst}\nДальше: фаза 1 (бриф) — docs/PHASES.md")
    return 0


def cmd_validate(a):
    from .templates import REGISTRY, load_project_templates
    from .textutil import word_count, segments
    from .lang import profile
    proj = load(resolve_project(a.project))
    lp = profile(proj.cfg["language"])
    load_project_templates(proj.root)
    errs, warns = [], []
    ids = set()
    words = 0
    for ch, d in proj.chapters:
        for s in d.get("scenes") or []:
            sid = s.get("id")
            if not sid or (ch, sid) in ids:
                errs.append(f"{ch}: сцена без id или повтор id ({sid})")
            ids.add((ch, sid))
            tp = s.get("template", "statement")
            if tp not in REGISTRY:
                errs.append(f"{ch}/{sid}: нет шаблона '{tp}' (есть: {', '.join(sorted(REGISTRY))})")
            else:
                unknown = set((s.get("params") or {})) - set(REGISTRY[tp].PARAMS)
                if unknown:
                    warns.append(f"{ch}/{sid}: неизвестные параметры {sorted(unknown)} для {tp}")
            lines = s.get("lines") or []
            if not lines and not s.get("min_duration"):
                errs.append(f"{ch}/{sid}: нет текста и не задан min_duration")
            for l in lines:
                words += word_count(l)
                if lp["foreign"] and re.search(lp["foreign"], l.replace("|", "")):
                    warns.append(f"{ch}/{sid}: «{l[:40]}…»: {lp['foreign_msg']}")
                if len(l) > 220:
                    warns.append(f"{ch}/{sid}: очень длинная строка ({len(l)} симв.) — разбейте на предложения")
                if any(len(x) > 90 for x in segments(l)):
                    warns.append(f"{ch}/{sid}: длинный бит без '|' — субтитры порежутся по словам")
    tgt = proj.cfg.get("target_duration")
    est = words / lp["wpm"] * 60
    print(f"Язык: {proj.cfg['language']}. Глав: {len(proj.chapters)}, сцен: {len(ids)}, слов: {words}, оценка речи ≈ {est:.0f} c")
    if tgt and est > tgt * 0.92:
        warns.append(f"Текста много для {tgt} c (оценка {est:.0f} c) — темп может упереться в потолок")
    for w in warns:
        print("  ⚠️ ", w)
    for e in errs:
        print("  ❌", e)
    print("OK" if not errs else "ЕСТЬ ОШИБКИ")
    return 1 if errs else 0


def _elevenlabs_guard(proj, yes):
    """Платный синтез: темп числом (подбор темпа синтезирует несколько раз) + оценка символов и подтверждение."""
    from . import tts
    from .textutil import tts_text
    tc = proj.cfg["tts"]
    if tc.get("rate", "auto") == "auto":
        raise SystemExit("ElevenLabs: задайте tts.rate числом (например 100) — подбор темпа оплачивал бы каждый прогон")
    cache = proj.bdir("tts")
    todo = [tts_text(l) for _, d in proj.chapters for sc in d.get("scenes") or [] for l in sc.get("lines") or []]
    new = [x for x in todo if not (cache / f"{tts.cache_key(x, tc, float(tc['rate']))}.wav").exists()]
    chars = sum(len(x) for x in new)
    print(f"ElevenLabs: строк к синтезу {len(new)} из {len(todo)}, символов ≈ {chars} (остальное — из кэша)")
    if chars and not yes:
        print("Платный синтез не запущен. Подтвердите: python -m studio voice <проект> --yes")
        return False
    return True


def cmd_voice(a):
    from .timing import layout
    proj = load(resolve_project(a.project))
    if proj.cfg["tts"]["backend"] == "elevenlabs" and not _elevenlabs_guard(proj, getattr(a, "yes", False)):
        return 3
    tl = layout(proj)
    print(f"Темп {tl['rate']:.0f}, длительность {tl['duration']:.2f} c, {len(tl['scenes'])} сцен, "
          f"{tl['wpm_speech']} слов/мин в речи")
    for s in tl["scenes"]:
        print(f"  {s['chapter']}/{s['id']:<6} {s['start']:7.2f}–{s['start'] + s['dur']:7.2f}  {s['template']:<12} "
              f"битов {len(s['beats'])}, субтитров {len(s['subs'])}")
    return 0


def cmd_stills(a):
    from .render import stills
    proj = load(resolve_project(a.project))
    times = [float(x) for x in a.times.split(",")] if a.times else None
    stills(proj, a.chapter, times)
    return 0


def cmd_render(a):
    from .render import render
    proj = load(resolve_project(a.project))
    render(proj, a.chapter, a.workers, force=a.force)
    return 0


def cmd_assemble(a):
    from .assemble import assemble
    assemble(load(resolve_project(a.project)), allow_stale=a.allow_stale)
    return 0


def cmd_qa(a):
    from .qa import run
    return 0 if run(load(resolve_project(a.project)), fast=a.fast) else 1


def cmd_all(a):
    for f in (cmd_validate, cmd_voice):
        if f(a):
            return 1
    from .render import render
    proj = load(resolve_project(a.project))
    render(proj, None, a.workers)
    from .assemble import assemble
    assemble(proj)
    from .qa import run
    return 0 if run(proj, fast=a.fast) else 1


def cmd_status(a):
    from .status import report
    report(load(resolve_project(a.project)))
    return 0


def cmd_templates(a):
    from .templates import REGISTRY, load_project_templates
    if a.project:
        load_project_templates(resolve_project(a.project))
    for n, c in sorted(REGISTRY.items()):
        print(f"\n## {n}\n{c.DOC}\n  биты: {c.BEATS}\n  параметры: {c.PARAMS}")
    return 0


def cmd_frame(a):
    from .render import frame_png
    proj = load(resolve_project(a.project))
    out = a.out or str(proj.qa_dir / f"frame_{a.t:.2f}.png")
    frame_png(proj, a.t, out)
    print(out)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m studio")
    sp = p.add_subparsers(dest="cmd", required=True)
    dr = sp.add_parser("doctor", help="проверить окружение и TTS")
    dr.add_argument("--lang", default=None, help="языки через запятую (ru,en); по умолчанию все из studio/lang.py")
    n = sp.add_parser("new", help="создать проект из шаблона")
    n.add_argument("topic"); n.add_argument("--slug"); n.add_argument("--format", default="vertical",
                                                                      choices=["vertical", "horizontal", "square"])
    n.add_argument("--duration", type=float, default=None, help="точная длительность, c (иначе — по речи)")
    n.add_argument("--lang", default="ru", help="язык ролика: ru | en | ... (studio/lang.py)")
    for name, h in (("validate", "проверить сценарий"), ("voice", "озвучка + тайминги"),
                    ("stills", "контрольные кадры"), ("render", "рендер сцен"), ("assemble", "сборка финала"),
                    ("qa", "проверка финала"), ("all", "voice→render→assemble→qa"), ("status", "фазы и следующий шаг"),
                    ("templates", "список шаблонов"), ("frame", "один кадр PNG")):
        q = sp.add_parser(name, help=h)
        q.add_argument("project", nargs="?")
        if name in ("stills", "render"):
            q.add_argument("--chapter")
        if name == "stills":
            q.add_argument("--times", help="глобальные времена через запятую")
        if name in ("render", "all"):
            q.add_argument("--workers", type=int)
        if name == "render":
            q.add_argument("--force", action="store_true")
        if name == "assemble":
            q.add_argument("--allow-stale", action="store_true")
        if name in ("qa", "all"):
            q.add_argument("--fast", action="store_true", help="без полного декодирования")
        if name in ("voice", "all"):
            q.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")
        if name == "frame":
            q.add_argument("t", type=float); q.add_argument("--out")
    a = p.parse_args(argv)
    from .tts import TTSUnavailable
    try:
        return globals()["cmd_" + a.cmd](a)
    except TTSUnavailable as e:
        print(f"❌ Синтез речи недоступен: {e}\n"
              "Ролик без озвучки не делаем: сообщите пользователю и предложите установку (docs/TTS.md).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
