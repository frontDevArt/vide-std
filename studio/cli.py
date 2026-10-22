"""python -m studio <команда> [проект] — единая точка входа студии."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .project import STUDIO_ROOT, load, resolve_project


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
        for name, want, have in pinned_mismatches():
            # другая версия Pillow/numpy = другие пиксели; не ошибка, но кэш и эталоны QA поплывут
            print(f"  ⚠️  {name} {have}, закреплена {want} -> pip install -r requirements.txt")
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


def _has_edge():
    import importlib.util
    return importlib.util.find_spec("edge_tts") is not None or bool(shutil.which("edge-tts"))


def default_backend(lang):
    """Голос нового проекта — первый доступный по дешёвой проверке (без сети и синтеза), иначе None.
    ElevenLabs платный: только для канала (есть channel/POSITIONING.md, ролики англоязычные) и с ключом в .env."""
    import os
    from . import tts  # noqa: F401 — подхватывает .env в окружение
    if (os.environ.get("ELEVENLABS_API_KEY", "").strip() and lang == "en"
            and (STUDIO_ROOT / "channel" / "POSITIONING.md").exists()):
        return "elevenlabs"
    if _has_edge():
        return "edge"
    if (STUDIO_ROOT / "tools" / "rhvoice" / "rhvoice").exists():
        return "rhvoice"
    return None


def cmd_new(a):
    backend = a.tts or default_backend(a.lang)
    if not backend:
        backend = "rhvoice"
        print("⚠️  нет доступного голоса (ключ ElevenLabs для канала, edge_tts, RHVoice) — записан rhvoice;\n"
              "   поставьте голос (python -m studio doctor, bash tools/setup_rhvoice.sh) или укажите --tts")
    slug = a.slug or slugify(a.topic)
    dst = STUDIO_ROOT / "projects" / slug
    if dst.exists():
        raise SystemExit(f"Уже есть: {dst}")
    shutil.copytree(STUDIO_ROOT / "projects" / "_template", dst)
    y = (dst / "project.yaml").read_text(encoding="utf-8")
    # JSON-строка — валидный YAML при любых кавычках и `: `/`#` в теме; комментарии заготовки сохраняются
    y = y.replace("topic: TODO", f"topic: {json.dumps(a.topic, ensure_ascii=False)}")
    y = y.replace("language: ru", f"language: {a.lang}")
    y = y.replace("format: vertical", f"format: {a.format}")
    y = y.replace("target_duration: null", f"target_duration: {a.duration if a.duration else 'null'}")
    # явно в project.yaml, а не «по умолчанию»: бэкенд входит в ключ кэша TTS и не должен зависеть от машины
    y = y.replace("  backend: rhvoice ", f"  backend: {backend} ", 1)
    (dst / "project.yaml").write_text(y, encoding="utf-8")
    print(f"Создан проект: {dst} (голос: {backend})\nДальше: фаза 1 (бриф) — docs/PHASES.md")
    return 0


def cmd_validate(a):
    from .templates import REGISTRY, load_project_templates
    from .textutil import word_count, segments, line_text, line_voice, AUDIO_TAG
    from .lang import profile
    proj = load(resolve_project(a.project))
    lp = profile(proj.cfg["language"])
    load_project_templates(proj.root)
    errs, warns = [], []
    ids = set()
    words = 0
    accents = []  # где переопределён голос: правило канала — 1–2 на ролик (крючок, вердикт)
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
            if s.get("voice"):
                accents.append(f"{ch}/{sid}")
                _validate_voice(proj, s["voice"], f"{ch}/{sid}", errs, warns)
            for item in lines:
                l = line_text(item)
                if isinstance(item, dict) and not l.strip():
                    errs.append(f"{ch}/{sid}: строка-словарь без text")
                if line_voice(item):
                    accents.append(f"{ch}/{sid}: «{l[:30]}…»")
                    _validate_voice(proj, line_voice(item), f"{ch}/{sid}", errs, warns)
                model = {**proj.cfg["tts"], **(s.get("voice") or {}), **line_voice(item)}.get("model", "")
                if AUDIO_TAG.search(l) and not str(model).startswith("eleven_v3"):
                    warns.append(f"{ch}/{sid}: «{l[:40]}…»: тег эмоции без model: eleven_v3 — будет прочитан вслух")
                words += word_count(l)
                if lp["foreign"] and re.search(lp["foreign"], l.replace("|", "")):
                    warns.append(f"{ch}/{sid}: «{l[:40]}…»: {lp['foreign_msg']}")
                if len(l) > 220:
                    warns.append(f"{ch}/{sid}: очень длинная строка ({len(l)} симв.) — разбейте на предложения")
                if any(len(x) > 90 for x in segments(l)):
                    warns.append(f"{ch}/{sid}: длинный бит без '|' — субтитры порежутся по словам")
    if len(accents) > 2:
        warns.append(f"голос переопределён {len(accents)} раз ({', '.join(accents)}) — правило канала: 1–2 акцента "
                     f"на ролик (крючок, вердикт), спокойный рассказчик — часть тона")
    _validate_style(proj, errs, warns)
    _validate_triggers(proj, errs, warns)
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


def _validate_voice(proj, v, where, errs, warns):
    """voice: сцены/строки (docs/TTS.md): только elevenlabs, известные ключи, диапазоны API, не быстрее rate_range."""
    from .tts import EL_VOICE_KEYS, EL_SPEED
    tc = proj.cfg["tts"]
    if not isinstance(v, dict):
        errs.append(f"{where}: voice должен быть словарём {{stability, style, speed, …}}")
        return
    if tc["backend"] != "elevenlabs":
        warns.append(f"{where}: voice действует только для tts.backend: elevenlabs — сейчас игнорируется")
    unknown = set(v) - set(EL_VOICE_KEYS)
    if unknown:
        errs.append(f"{where}: неизвестные ключи voice {sorted(unknown)} (есть: {', '.join(EL_VOICE_KEYS)})")
    for k in ("stability", "similarity_boost", "style"):
        if k in v and not (isinstance(v[k], (int, float)) and 0 <= v[k] <= 1):
            errs.append(f"{where}: voice.{k} = {v[k]!r}, нужно число 0–1")
    if "speed" in v:
        sp, hi = v["speed"], tc.get("rate_range", [98, 125])[1] / 100
        if not (isinstance(sp, (int, float)) and EL_SPEED[0] <= sp <= EL_SPEED[1]):
            errs.append(f"{where}: voice.speed = {sp!r}, API принимает {EL_SPEED[0]}–{EL_SPEED[1]}")
        elif sp > hi:
            errs.append(f"{where}: voice.speed {sp} быстрее потолка rate_range ({hi:g}) — речь не ускоряем")
    if "model" in v:
        warns.append(f"{where}: voice.model = {v['model']} — эксперимент: тембр и таймкоды сверить на слух и в stills")


def _validate_style(proj, errs, warns):
    """style.mood / style.overrides / glow глав (channel/STYLE.md §14): accent2 не спорит с вердиктами и бренд-цианом."""
    from . import gfx as G
    st = proj.cfg["style"]
    pal = G.PALETTES.get(st.get("palette", "neon"), G.PALETTES["neon"])
    try:
        mc = G.mood_colors(st.get("mood"), st.get("overrides"), base=pal)
    except ValueError as e:
        errs.append(f"style: {e}")
        return
    if (st.get("mood") or st.get("overrides")) and st.get("palette") != "lab":
        warns.append("style.mood/overrides рассчитаны на palette: lab")
    near = lambda a, b: sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5 < 48
    for k in ("true", "half", "myth", "noev", "accent"):
        if k in pal and near(mc["accent2"], pal[k]):
            what = "бренд-цианом accent" if k == "accent" else f"цветом вердикта {k}"
            errs.append(f"style: accent2 #{'%02X%02X%02X' % tuple(mc['accent2'])} совпадает с {what} "
                        f"#{'%02X%02X%02X' % tuple(pal[k])} — выберите другое настроение или overrides.accent2")
    for ch, d in proj.chapters:
        try:
            G.chapter_glow(d.get("glow"))
        except ValueError as e:
            errs.append(f"{ch}: {e}")


def _validate_triggers(proj, errs, warns):
    """Триггеры at: (B8) — по словам озвучки, только если timeline.json актуален (иначе слова старые)."""
    from .lab import trigger_errors
    from .templates import REGISTRY
    from .timing import source_hash
    p = proj.build / "timeline.json"
    if not p.exists():
        return
    tl = json.loads(p.read_text(encoding="utf-8"))
    if tl.get("src") != source_hash(proj):
        warns.append("timeline.json устарел — триггеры at: проверит voice")
        return
    errs += trigger_errors(tl["scenes"], REGISTRY)


def _elevenlabs_guard(proj, yes):
    """Платный синтез: темп числом (подбор темпа синтезирует несколько раз) + оценка символов и подтверждение."""
    from . import tts
    from .timing import line_jobs
    tc = proj.cfg["tts"]
    if tc.get("rate", "auto") == "auto":
        raise SystemExit("ElevenLabs: задайте tts.rate числом (например 100) — подбор темпа оплачивал бы каждый прогон")
    cache = proj.bdir("tts")
    todo = [j for _, d in proj.chapters for sj in line_jobs(d.get("scenes") or []) for j in sj]
    new = [text for _, text, prev, nxt, voice in todo
           if not (cache / f"{tts.cache_key(text, tc, float(tc['rate']), prev, nxt, voice)}.wav").exists()]
    chars = sum(len(x) for x in new)  # previous_text/next_text — контекст, в символы не входит
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
    from .lab import trigger_errors
    from .templates import REGISTRY, load_project_templates
    load_project_templates(proj.root)
    errs = trigger_errors(tl["scenes"], REGISTRY)
    for e in errs:
        print("  ❌", e)
    if errs:
        print(f"Триггеры at: не найдено {len(errs)} — элементы появятся не в такт. Поправьте at или текст и повторите voice")
    return 1 if errs else 0


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


def cmd_demo(a):
    """Демо стиля 10–15 с (channel/STYLE.md §14) в projects/<slug>-demo/: стиль, формат, язык и голос — из проекта,
    сценарий — projects/<slug>/demo/ch01.yaml (иначе заготовка _template/demo), шаблоны проекта — копией."""
    import yaml
    src = resolve_project(a.project)
    if src.name.endswith("-demo"):
        raise SystemExit("Это уже демо-проект — укажите исходный")
    script = src / "demo" / "ch01.yaml"
    if not script.exists():
        script = STUDIO_ROOT / "projects" / "_template" / "demo" / "ch01.yaml"
        print(f"⚠️  нет {src.name}/demo/ch01.yaml — беру заготовку {script.relative_to(STUDIO_ROOT)} "
              "(без метафоры ролика; язык заготовки — en)")
    dst = src.parent / f"{src.name}-demo"
    (dst / "script").mkdir(parents=True, exist_ok=True)
    with open(src / "project.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.update(title=f"style demo: {cfg.get('title', src.name)}", target_duration=None, chapters=["ch01"])
    with open(dst / "project.yaml", "w", encoding="utf-8") as f:
        f.write(f"# Сгенерировано `python -m studio demo {src.name}` — правьте исходный проект и demo/ch01.yaml.\n")
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    shutil.copyfile(script, dst / "script" / "ch01.yaml")
    if (src / "templates").exists():
        shutil.copytree(src / "templates", dst / "templates", dirs_exist_ok=True)
    print(f"Демо-проект: {dst}")
    if a.no_render:
        return 0
    a.project, a.fast = str(dst), False
    rc = cmd_all(a)
    if not (dst / "build" / "timeline.json").exists():
        return rc or 1
    from .timing import load_timeline
    dur = load_timeline(load(dst))["duration"]
    if not 10 <= dur <= 15.5:
        print(f"⚠️  демо {dur:.1f} c — нужно 10–15 c: поправьте текст demo/ch01.yaml")
    print(f"Демо: {load(dst).final_path()} ({dur:.1f} c) — показать пользователю и ждать утверждения")
    return rc


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


def cmd_selftest(a):
    from .selftest import run
    return 0 if run(full=a.full, keep=a.keep, workers=a.workers) else 1


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
    n.add_argument("--tts", choices=["elevenlabs", "edge", "rhvoice", "piper", "fake"],
                   help="голос; без флага — первый доступный: elevenlabs (канал + ключ) → edge → rhvoice")
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
    dm = sp.add_parser("demo", help="демо стиля 10–15 с в projects/<slug>-demo/ (STYLE §14)")
    dm.add_argument("project")
    dm.add_argument("--no-render", action="store_true", help="только создать проект демо")
    dm.add_argument("--workers", type=int)
    dm.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")
    st = sp.add_parser("selftest", help="регресс студии офлайн: gallery → voice (fake) → render → assemble → qa → golden")
    st.add_argument("--full", action="store_true", help="полная цепочка и на vertical (~2,5 мин), а не только horizontal")
    st.add_argument("--keep", action="store_true", help="не удалять рабочую папку (посмотреть qa/*.png)")
    st.add_argument("--workers", type=int)
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
