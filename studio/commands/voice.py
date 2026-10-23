"""voice — озвучка + тайминги (timeline.json)."""
from __future__ import annotations

from . import add_out, project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "voice", "озвучка + тайминги")
    q.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")
    add_out(q)


def elevenlabs_guard(proj, yes):
    """Платный синтез: темп числом (подбор темпа синтезирует несколько раз) + оценка символов и подтверждение."""
    from .. import tts
    from ..timing import line_jobs
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


def run(a):
    from ..timing import layout
    base = load(resolve_project(a.project))
    if base.cfg["tts"]["backend"] == "elevenlabs" and not elevenlabs_guard(base, getattr(a, "yes", False)):
        return 3
    # выходы (ROADMAP B3): синтез один — build/tts/, раскладка (субтитры по ширине кадра) — у каждого своя
    outs = base.targets(getattr(a, "out", None))
    tls = [layout(proj) for proj in outs]
    for proj, tl in zip(outs, tls):
        print(f"{'[' + proj.out + '] ' if proj.out else ''}Темп {tl['rate']:.0f}, длительность {tl['duration']:.2f} c, "
              f"{len(tl['scenes'])} сцен, {tl['wpm_speech']} слов/мин в речи")
    proj, tl = outs[0], tls[0]  # замер голоса, сцены и триггеры одинаковы у всех выходов
    from ..calibration import calibrate
    for w in calibrate(proj, tl):
        print("  ⚠️ ", w)
    for s in tl["scenes"]:
        print(f"  {s['chapter']}/{s['id']:<6} {s['start']:7.2f}–{s['start'] + s['dur']:7.2f}  {s['template']:<12} "
              f"битов {len(s['beats'])}, субтитров {len(s['subs'])}")
    from ..packs import REGISTRY, load_project_templates
    from ..packs.lab import trigger_errors
    load_project_templates(proj.root)
    errs = trigger_errors(tl["scenes"], REGISTRY)
    for e in errs:
        print("  ❌", e)
    if errs:
        print(f"Триггеры at: не найдено {len(errs)} — элементы появятся не в такт. Поправьте at или текст и повторите voice")
    return 1 if errs else 0
