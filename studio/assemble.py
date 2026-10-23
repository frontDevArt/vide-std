"""Сборка: сцены -> финал. Видео склеивается без перекодирования (одинаковые параметры кодека во всех сценах)
прямо из build/render/, звук — один общий микс на весь ролик. Файлы глав build/chapters/chNN.mp4 (копия сцен
главы) — только по `chapters=True` (`assemble --chapters`). draft — из чернового рендера (`render --draft`)
в build/final/<slug>.draft.mp4, чистовой финал и главы не трогаются. WAV микса живут только во временной папке."""
from __future__ import annotations

import tempfile
from pathlib import Path

from .audio import ff, mix
from .project import Project
from .render import is_fresh, prepare, scene_out


def _concat(lst: Path, files, out: Path, *args):
    lst.write_text("".join(f"file '{f}'\n" for f in files))
    ff(["-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), *args, str(out)])


def assemble(proj: Project, log=print, allow_stale=False, draft=False, chapters=False) -> str:
    tl, _ = prepare(proj, draft)
    suf = ".draft" if draft else ""
    stale = [f"{s['chapter']}/{s['id']}" for s in tl["scenes"] if not is_fresh(proj, s)]
    if stale and not allow_stale:
        raise SystemExit("Не отрендерены/устарели сцены: " + ", ".join(stale[:12]) +
                         ("…" if len(stale) > 12 else "") + "\nСначала: python -m studio render <проект>"
                         + (" --draft" if draft else ""))
    for ch, _ in proj.chapters:
        sc = [s for s in tl["scenes"] if s["chapter"] == ch]
        if sc:
            if chapters:
                _concat(proj.bdir("chapters") / f"{ch}{suf}.txt", [scene_out(proj, s) for s in sc],
                        proj.bdir("chapters") / f"{ch}{suf}.mp4", "-c", "copy")
            log(f"Глава {ch}: {len(sc)} сцен")
    D = tl["total_frames"] / tl["fps"]
    final = proj.final_path().with_suffix(f"{suf}.mp4")
    with tempfile.TemporaryDirectory() as tmp:  # список сцен и промежуточные WAV микса — удаляются после склейки
        audio = mix(proj, Path(tmp), log)
        _concat(Path(tmp) / "scenes.txt", [scene_out(proj, s) for s in tl["scenes"]], final,
                "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-ar", "48000", "-ac", "2", "-t", f"{D:.3f}", "-movflags", "+faststart")
    log(f"Готово: {final}")
    return str(final)
