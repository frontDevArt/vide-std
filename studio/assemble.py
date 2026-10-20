"""Сборка: сцены -> главы -> финал. Видео склеивается без перекодирования (одинаковые параметры
кодека во всех сценах), звук — один общий микс на весь ролик."""
from __future__ import annotations

from .audio import ff, mix
from .project import Project
from .render import is_fresh, prepare, scene_out


def assemble(proj: Project, log=print, allow_stale=False) -> str:
    tl, _ = prepare(proj)
    stale = [f"{s['chapter']}/{s['id']}" for s in tl["scenes"] if not is_fresh(proj, s)]
    if stale and not allow_stale:
        raise SystemExit("Не отрендерены/устарели сцены: " + ", ".join(stale[:12]) +
                         ("…" if len(stale) > 12 else "") + "\nСначала: python -m studio render <проект>")
    chapters = []
    for ch, _ in proj.chapters:
        sc = [s for s in tl["scenes"] if s["chapter"] == ch]
        if not sc:
            continue
        lst = proj.bdir("chapters") / f"{ch}.txt"
        lst.write_text("".join(f"file '{scene_out(proj, s)}'\n" for s in sc))
        out = proj.bdir("chapters") / f"{ch}.mp4"
        ff(["-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
        chapters.append(out)
        log(f"Глава {ch}: {len(sc)} сцен")
    audio = mix(proj, log)
    allv = proj.bdir("chapters") / "_all.txt"
    allv.write_text("".join(f"file '{c}'\n" for c in chapters))
    D = tl["total_frames"] / tl["fps"]
    final = proj.final_path()
    ff(["-v", "error", "-f", "concat", "-safe", "0", "-i", str(allv), "-i", audio,
        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-t", f"{D:.3f}", "-movflags", "+faststart", str(final)])
    log(f"Готово: {final}")
    return str(final)
