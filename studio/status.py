"""Состояние проекта по фазам + следующий шаг. Источник правды — файлы, а не память сессии."""
from __future__ import annotations

from .project import Project
from .textutil import word_count, line_text


def _mt(p):
    return p.stat().st_mtime if p.exists() else 0


def phases(proj: Project):
    r = proj.root
    cfg = proj.cfg
    out = []
    brief_ok = bool(cfg.get("topic")) and "TODO" not in str(cfg.get("title", "TODO")) and "TODO" not in str(cfg.get("topic"))
    out.append(("1 Бриф", brief_ok, "project.yaml: title, topic, format, target_duration, голос"))
    ol = r / "outline.md"
    outline_ok = ol.exists() and "TODO" not in ol.read_text(encoding="utf-8")
    out.append(("2 План (outline.md)", outline_ok, "главы, длительности, бюджет слов"))
    listed = cfg.get("chapters") or []
    have = [c for c, _ in proj.chapters]
    missing = [c for c in listed if c not in have]
    out.append(("3 Сценарий", bool(listed) and not missing,
                f"глав в плане {len(listed)}, написано {len(have)}" + (f"; нет: {', '.join(missing)}" if missing else "")))
    tl = proj.build / "timeline.json"
    voice_ok = False
    if tl.exists():
        import json
        from .timing import source_hash
        voice_ok = json.loads(tl.read_text(encoding="utf-8")).get("src") == source_hash(proj)
    out.append(("4 Озвучка и тайминг", voice_ok, "build/timeline.json актуален" if voice_ok else "нужно: voice"))
    st = list((proj.qa_dir).glob("stills_*.png"))
    stills_ok = voice_ok and bool(st) and max(_mt(p) for p in st) >= _mt(tl)
    out.append(("5 Контрольные кадры", stills_ok, "qa/stills_*.png посмотрены?"))
    fresh = total = 0
    if voice_ok:
        try:
            from .render import is_fresh, prepare
            tld, _ = prepare(proj)
            total = len(tld["scenes"])
            fresh = sum(1 for s in tld["scenes"] if is_fresh(proj, s))
        except SystemExit:
            pass
    out.append(("6 Рендер сцен", voice_ok and total > 0 and fresh == total,
                f"{fresh}/{total} сцен актуальны" if voice_ok else "сначала актуализировать озвучку"))
    fin = proj.final_path()
    scene_files = list((proj.build / "render").glob("*/*.mp4")) if (proj.build / "render").exists() else []
    asm_ok = fin.exists() and fresh == total and total > 0 and _mt(fin) >= max([_mt(p) for p in scene_files] + [0])
    out.append(("7 Сборка", asm_ok, str(fin.relative_to(r)) if fin.exists() else "нет финала"))
    rep = proj.qa_dir / "report.md"
    qa_ok = asm_ok and rep.exists() and _mt(rep) >= _mt(fin) and "Итог: **PASS**" in rep.read_text(encoding="utf-8")
    out.append(("8 QA", qa_ok, "qa/report.md" if rep.exists() else "не запускался"))
    return out


NEXT = {
    "1 Бриф": "Заполни project.yaml (фаза 1 в docs/PHASES.md).",
    "2 План (outline.md)": "Напиши outline.md: главы, хронометраж, бюджет слов (фаза 2).",
    "3 Сценарий": "Пиши следующую главу script/<chNN>.yaml, затем `python -m studio validate` (фаза 3).",
    "4 Озвучка и тайминг": "`python -m studio voice <проект>` (фаза 4).",
    "5 Контрольные кадры": "`python -m studio stills <проект> [--chapter chNN]` и посмотри PNG (фаза 5).",
    "6 Рендер сцен": "`python -m studio render <проект>` в фоне, можно по главам (фаза 6).",
    "7 Сборка": "`python -m studio assemble <проект>` (фаза 7).",
    "8 QA": "`python -m studio qa <проект>` и открой qa/*.png (фаза 8).",
}


def pace(proj: Project):
    """(слов в сценарии, слов/мин, откуда темп): замер из timeline.json после voice, иначе wpm языка."""
    words = sum(word_count(line_text(l)) for _, d in proj.chapters for s in d.get("scenes") or []
                for l in s.get("lines") or [])
    tl = proj.build / "timeline.json"
    if tl.exists():
        import json
        wpm = json.loads(tl.read_text(encoding="utf-8")).get("wpm_speech")
        if wpm:
            return words, wpm, "замер timeline.json"
    from .lang import profile
    lang = proj.cfg.get("language")
    return words, profile(lang)["wpm"], f"язык {lang}"


def report(proj: Project, log=print):
    ph = phases(proj)
    words, wpm, src = pace(proj)
    log(f"Проект: {proj.slug} — {proj.cfg.get('title', '')}")
    log(f"Формат {proj.cfg['format']} {proj.size[0]}×{proj.size[1]}, {proj.fps} fps; "
        f"цель {proj.cfg.get('target_duration') or 'по речи'}; слов в сценарии: {words} "
        f"(~{words / wpm:.1f} мин речи при {wpm:g} слов/мин, {src})")
    nxt = None
    for name, ok, det in ph:
        log(f"  {'✅' if ok else '⬜'} {name}: {det}")
        if not ok and nxt is None:
            nxt = name
    log("Следующий шаг: " + (NEXT[nxt] if nxt else "всё готово 🎬"))
    return ph
