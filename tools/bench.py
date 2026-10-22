"""Замеры скорости рендера (REFACTOR_PLAN P0.8) — точка отсчёта для этапов 3–4, итоги в docs/history/BENCH.md.

  python tools/bench.py templates [--format horizontal|vertical] [--frames 48]
      кадров/с по каждому шаблону фикстуры gallery, 1 процесс, без кодирования; разбивка кадра по фазам
      (фон, рисование шаблона, камера, субтитры, RGB-байты для ffmpeg).
  python tools/bench.py project <проект> [--workers N]
      полный рендер + assemble копии проекта во временной папке (голос и timeline.json берутся из его build/,
      синтеза нет), время и размер build/ по папкам. Сам проект не трогается.

Офлайн, денег не тратит: gallery — голос fake, у проекта — готовый кэш tts.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from studio import gfx as G  # noqa: E402
from studio import project, render, subs, timing  # noqa: E402
from studio.selftest import make_gallery, pin_fonts  # noqa: E402

PHASES = ("bg", "draw", "camera", "subs", "rgb")


def _frame_phases(ctx, tpl, scene, f, sub_size, acc):
    """Тот же кадр, что render.frame + конвертация для ffmpeg, с замером каждой фазы."""
    fps = ctx["fps"]
    t, T = f / fps, (scene["start_frame"] + f) / fps
    c0 = time.perf_counter()
    glow = render.glow_at(scene, t)
    bg = render._bg(ctx["W"], ctx["H"], ctx["style"])
    img = bg.frame(T, glow) if glow else bg.frame(T)
    c1 = time.perf_counter()
    if getattr(tpl, "camera", False) and ctx["style"].camera:
        from studio.packs.lab.background import composite_camera
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        tpl.draw(layer, t, T)
        c2 = time.perf_counter()
        composite_camera(img, layer, T)
    else:
        tpl.draw(img, t, T)
        c2 = time.perf_counter()
    c3 = time.perf_counter()
    render.draw_subs(img, scene, t, sub_size, ctx["W"], ctx["H"], ctx["style"])
    c4 = time.perf_counter()
    img.convert("RGB").tobytes()
    c5 = time.perf_counter()
    for k, dt in zip(PHASES, (c1 - c0, c2 - c1, c3 - c2, c4 - c3, c5 - c4)):
        acc[k] += dt


def bench_templates(fmt, n_frames):
    pin_fonts()
    work = Path(tempfile.mkdtemp(prefix="studio-bench-"))
    try:
        root = make_gallery(work / "gallery", fmt)
        proj = project.load(root)
        with contextlib.redirect_stdout(io.StringIO()):
            timing.layout(proj, log=lambda *a, **k: None)
            tl, ctx = render.prepare(proj)
        sub_size = subs.font_size(proj)
        print(f"gallery {fmt} {ctx['W']}×{ctx['H']}, 1 процесс, до {n_frames} кадров на сцену равномерно, без кодирования")
        print("| шаблон | сцена | кадров | кадр/с | мс/кадр | фон | шаблон | камера | субтитры | RGB |")
        print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        tot_n, tot_t = 0, 0.0
        for s in tl["scenes"]:
            tpl = render.make_template(ctx, s)
            step = max(1, s["n_frames"] // n_frames)
            fs = list(range(0, s["n_frames"], step))[:n_frames]
            render.frame(ctx, tpl, s, fs[0], sub_size)  # прогрев: шрифты, спрайты, фон
            acc = dict.fromkeys(PHASES, 0.0)
            for f in fs:
                _frame_phases(ctx, tpl, s, f, sub_size, acc)
            dt = sum(acc.values())
            tot_n, tot_t = tot_n + len(fs), tot_t + dt
            pct = " | ".join(f"{acc[k] / dt * 100:.0f} %" if acc[k] / dt >= 0.005 else "—" for k in PHASES)
            print(f"| `{s['template']}` | {s['chapter']}/{s['id']} | {len(fs)} | {len(fs) / dt:.1f} | "
                  f"{dt / len(fs) * 1000:.0f} | {pct} |")
        print(f"\nВсего: {tot_n} кадров за {tot_t:.1f} с — {tot_n / tot_t:.1f} кадр/с в среднем")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _size(p: Path):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def bench_project(src, workers):
    from studio.assemble import assemble
    src = project.load(src).root
    if not (src / "build" / "timeline.json").exists():
        raise SystemExit(f"Нет {src / 'build' / 'timeline.json'} — сначала voice")
    work = Path(tempfile.mkdtemp(prefix="studio-bench-"))  # короткий путь: у ffmpeg на Windows лимит 260 символов
    try:
        dst = work / src.name
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("build", "logs", "qa", "demo", "*.log"))
        (dst / "build").mkdir()
        shutil.copy2(src / "build" / "timeline.json", dst / "build")
        shutil.copytree(src / "build" / "tts", dst / "build" / "tts")
        proj = project.load(dst)
        tl = render.load_timeline(proj)
        workers = workers or proj.cfg["render"].get("workers") or render.default_workers()
        print(f"{src.name}: {tl['size'][0]}×{tl['size'][1]}, {len(tl['scenes'])} сцен, {tl['total_frames']} кадров "
              f"({tl['total_frames'] / tl['fps']:.0f} с), процессов: {workers}; копия в {work}")
        t0 = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            render.render(proj, workers=workers, log=lambda *a, **k: None)
        t_render = time.time() - t0
        t0 = time.time()
        with contextlib.redirect_stdout(io.StringIO()):
            assemble(proj, log=lambda *a, **k: None)
        t_asm = time.time() - t0
        print(f"render: {t_render:.0f} с ({tl['total_frames'] / t_render:.1f} кадр/с), assemble: {t_asm:.0f} с")
        b = proj.build
        print("build/: " + ", ".join(f"{d.name} {_size(d) / 2**20:.0f} МБ" for d in sorted(b.iterdir()) if d.is_dir())
              + f"; всего {_size(b) / 2**20:.0f} МБ")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("templates")
    t.add_argument("--format", default="horizontal", choices=("horizontal", "vertical", "square"))
    t.add_argument("--frames", type=int, default=48)
    p = sp.add_parser("project")
    p.add_argument("project")
    p.add_argument("--workers", type=int)
    a = ap.parse_args(argv)
    if a.cmd == "templates":
        bench_templates(a.format, a.frames)
    else:
        bench_project(a.project, a.workers)


if __name__ == "__main__":
    main()
