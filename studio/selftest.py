"""python -m studio selftest — регресс студии офлайн (REFACTOR_PLAN P0.5), заменяет ручной `new regress` → `demo`.

Фикстура gallery (все шаблоны, 2 главы) → validate → voice (fake) → render → assemble → qa → сравнение с golden
(tests/golden/, P0.4): timeline.json и .srt байт в байт, кадры — с допуском, и ещё раз те же кадры, вынутые из
готового MP4 (ловит расхождение рендера в воркерах с кадром в процессе). Полная цепочка — на horizontal, vertical —
voice и кадры без кодирования (`--full` — цепочка на обоих, ~2,5 мин). Golden здесь только сравнивается;
обновить — pytest tests/test_golden.py --update-golden.
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .project import STUDIO_ROOT

GOLDEN = STUDIO_ROOT / "tests" / "golden"
DIFF = STUDIO_ROOT / "tests" / ".golden-diff"
FIXTURE = STUDIO_ROOT / "tests" / "fixtures" / "gallery"
KIND_DEMOS = STUDIO_ROOT / "tests" / "fixtures" / "kinds"  # демо типов роликов (ROADMAP C1)
FONT = STUDIO_ROOT / "assets" / "fonts" / "Manrope-VF.ttf"
FORMATS = ("horizontal", "vertical")
FRACS = (0.3, 0.85)  # кадры сцены: посреди входа и почти в конце, когда всё вышло
MAX_DIFF, MEAN_DIFF = 2, 0.1  # из 255: кадр в процессе против golden — максимум по пикселю и среднее
# Кадр из MP4 (yuv420p, crf 18) против golden. Замер 2026-10-22: шум кодека — средняя 1,1–1,3, макс ≤ 43;
# сдвиг на 1 кадр — макс ≥ 121; чужая сцена — средняя ≥ 2,1. Допуск посередине.
MP4_MAX, MP4_MEAN = 80, 1.6
BUDGET = 120  # с: P0.5 — укладываться в 2 минуты


def pin_fonts():
    """Шрифты только из assets/fonts: golden снят с ними, системные шрифты кадры не меняют. Воркеры рендера
    наследуют os.environ."""
    from . import gfx
    for w in gfx.WEIGHTS:
        os.environ["STUDIO_FONT_" + w.upper()] = str(FONT)
    gfx._font_file.cache_clear()
    gfx.font.cache_clear()


def make_gallery(dst: Path, fmt: str = "horizontal") -> Path:
    """Копия фикстуры gallery (P0.2) в dst с нужным форматом: vertical | horizontal | square | portrait."""
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("format: horizontal", f"format: {fmt}"), encoding="utf-8")
    return dst


def frame_name(s, f):
    return f"{s['chapter']}-{s['id']}-f{f:04d}.png"


def golden_points(tl):
    """[(имя, глобальный номер кадра)] — по FRACS на каждую сцену."""
    return [(frame_name(s, f), s["start_frame"] + f) for s in tl["scenes"]
            for f in (int(s["n_frames"] * fr) for fr in FRACS)]


def golden_frames(proj):
    """{имя: кадр в половинном разрешении} — по FRACS на каждую сцену, рисуется в процессе (без кодека)."""
    from . import render, subs
    tl, ctx = render.prepare(proj)
    sub_size = subs.font_size(proj)
    out = {}
    for s in tl["scenes"]:
        tpl = render.make_template(ctx, s)
        for fr in FRACS:
            f = int(s["n_frames"] * fr)
            out[frame_name(s, f)] = render.frame(ctx, tpl, s, f, sub_size).convert("RGB").reduce(2)
    return out


def mp4_frames(path, tl):
    """Те же кадры, вынутые из готового MP4, в половинном разрешении."""
    pts = golden_points(tl)
    W, H = tl["size"]
    sel = "+".join(f"eq(n\\,{n})" for _, n in pts)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"select='{sel}'", "-fps_mode", "passthrough",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, stdin=subprocess.DEVNULL)
    if r.returncode:
        raise RuntimeError(f"ffmpeg: {r.stderr.decode(errors='replace')[-400:]}")
    size = W * H * 3
    got = len(r.stdout) // size
    if got != len(pts):
        raise RuntimeError(f"из MP4 вынуто {got} кадров из {len(pts)}")
    return {name: Image.frombytes("RGB", (W, H), r.stdout[i * size:(i + 1) * size]).reduce(2)
            for i, (name, _) in enumerate(pts)}


def frame_diff(golden, img, max_diff=MAX_DIFF, mean_diff=MEAN_DIFF):
    """(не в допуске, макс, средняя, |разница| по пикселям)."""
    g = np.asarray(Image.open(golden).convert("RGB"), dtype=np.int16)
    a = np.asarray(img, dtype=np.int16)
    if g.shape != a.shape:
        return True, 255, 255.0, np.full(a.shape, 255, np.int16)
    d = np.abs(a - g)
    mx, mean = int(d.max()), float(d.mean())
    return mx > max_diff or mean > mean_diff, mx, mean, d


def compare_frames(frames, gdir, ddir, max_diff=MAX_DIFF, mean_diff=MEAN_DIFF):
    """Ошибки сравнения кадров с golden; при расхождении факт и карта разницы ×32 — в ddir."""
    bad = [f"{n}: лишний golden" for n in sorted(p.name for p in gdir.glob("*.png") if p.name not in frames)]
    worst = (0, 0.0)
    for n, img in frames.items():
        g = gdir / n
        if not g.exists():
            bad.append(f"{n}: нет golden")
            continue
        fail, mx, mean, d = frame_diff(g, img, max_diff, mean_diff)
        worst = (max(worst[0], mx), max(worst[1], mean))
        if fail:
            ddir.mkdir(parents=True, exist_ok=True)
            img.save(ddir / n)
            Image.fromarray(np.clip(d * 32, 0, 255).astype(np.uint8)).save(ddir / n.replace(".png", "_diff.png"))
            bad.append(f"{n}: макс {mx}, средняя {mean:.3f}")
    return bad, worst


def bytes_diff(golden: Path, actual: bytes):
    """None, если совпадает байт в байт; иначе первая отличающаяся строка."""
    if not golden.exists():
        return f"нет {golden.relative_to(STUDIO_ROOT)}"
    if golden.read_bytes() == actual:
        return None
    exp, act = golden.read_text(encoding="utf-8").splitlines(), actual.decode("utf-8").splitlines()
    i = next((i for i, (a, b) in enumerate(zip(exp, act)) if a != b), min(len(exp), len(act)))
    return (f"{golden.relative_to(STUDIO_ROOT)}, строка {i + 1}: golden «{exp[i] if i < len(exp) else '<конец>'}», "
            f"сейчас «{act[i] if i < len(act) else '<конец>'}»")


class _Run:
    def __init__(self, log):
        self.log, self.fails, self.t0 = log, [], time.time()

    @contextlib.contextmanager
    def step(self, name):
        """Шаг с замером; вывод движка — в буфер, показывается только при падении шага."""
        t, buf = time.time(), io.StringIO()
        res = {"errors": []}
        try:
            with contextlib.redirect_stdout(buf):
                yield res
        except (Exception, SystemExit) as e:
            res["errors"].append(f"{type(e).__name__}: {e}")
        errs = res["errors"]
        self.log(f"  {'✅' if not errs else '❌'} {name} — {time.time() - t:.1f} c" + (f" ({res['note']})" if res.get("note") else ""))
        if errs:
            tail = buf.getvalue().strip().splitlines()[-15:]
            for e in errs[:20]:
                self.log(f"      {e}")
            for line in tail:
                self.log(f"      | {line}")
            self.fails.append(name)


def _quiet(*_a, **_k):
    pass


def run(full=False, keep=False, workers=None, log=print) -> bool:
    from . import cli, project, render, timing
    from .assemble import assemble
    from .qa import run as qa_run
    pin_fonts()
    work = Path(tempfile.mkdtemp(prefix="studio-selftest-"))  # короткий путь: у ffmpeg на Windows лимит 260 символов
    r = _Run(log)
    log(f"selftest: фикстура gallery, голос fake, офлайн; рабочая папка {work}")
    for fmt in FORMATS:
        chain = full or fmt == FORMATS[0]
        log(f"{fmt}: {'полная цепочка' if chain else 'voice + кадры без кодирования'}")
        root = make_gallery(work / fmt / "gallery", fmt)  # slug = gallery: от него имя .srt в golden
        gold = GOLDEN / fmt
        shutil.rmtree(DIFF / fmt, ignore_errors=True)
        with r.step("validate") as st:
            if cli.main(["validate", str(root)]):
                st["errors"].append("validate вернул ошибку")
        with r.step("voice (fake) → timeline.json, .srt = golden") as st:
            proj = project.load(root)
            tl = timing.layout(proj, log=_quiet)
            for g, f in ((gold / "timeline.json", proj.build / "timeline.json"),
                         (gold / "gallery.srt", proj.bdir("final") / "gallery.srt")):
                e = bytes_diff(g, f.read_bytes())
                if e:
                    st["errors"].append(e)
        if st["errors"]:
            continue  # без своего timeline кадры и цепочка сравнивать не с чем
        with r.step("кадры в процессе = golden") as st:
            st["errors"], worst = compare_frames(golden_frames(proj), gold / "frames", DIFF / fmt)
            st["note"] = f"{len(golden_points(tl))} кадров, худший: макс {worst[0]}, средняя {worst[1]:.3f}"
        if not chain:
            continue
        with r.step("render") as st:
            render.render(proj, workers=workers, log=_quiet)
            st["note"] = f"{tl['total_frames']} кадров"
        if st["errors"]:
            continue
        with r.step("assemble") as st:
            assemble(proj, log=_quiet)
        if st["errors"]:
            continue
        with r.step("qa") as st:
            lines = []
            if not qa_run(proj, log=lines.append):
                st["errors"] += [x for x in lines if x.startswith("[FAIL]")]
        with r.step("кадры из MP4 = golden") as st:
            st["errors"], worst = compare_frames(mp4_frames(proj.final_path(), tl), gold / "frames", DIFF / fmt / "mp4",
                                                 MP4_MAX, MP4_MEAN)
            st["note"] = f"допуск макс {MP4_MAX}, средняя {MP4_MEAN}; худший: макс {worst[0]}, средняя {worst[1]:.3f}"
    total = time.time() - r.t0
    ok = not r.fails
    if ok and not keep:
        shutil.rmtree(work, ignore_errors=True)
    over = "" if total <= BUDGET or full else f" ⚠️ дольше бюджета {BUDGET} c (P0.5)"
    log(f"{'✅ selftest пройден' if ok else '❌ selftest не пройден: ' + ', '.join(dict.fromkeys(r.fails))} "
        f"за {total:.0f} c{over}")
    if not ok or keep:
        log(f"  рабочая папка оставлена: {work}" + (f"; кадры с расхождением — {DIFF}" if not ok else ""))
    return ok


def run_kinds(keep=False, workers=None, log=print) -> bool:
    """`selftest --kinds` (ROADMAP C1): демо каждого готового типа ролика (tests/fixtures/kinds/<тип>/) — validate →
    voice → render → assemble → qa, итог QA — PASS. Golden нет: проверка — отчёт QA (кадры — в qa/ при --keep)."""
    from . import cli, kinds, project, render, timing
    from .assemble import assemble
    from .qa import run as qa_run
    pin_fonts()
    work = Path(tempfile.mkdtemp(prefix="studio-kinds-"))
    r = _Run(log)
    ready = [k for k in kinds.KINDS.values() if not k.needs]
    log(f"selftest --kinds: {len(ready)} типов, офлайн; рабочая папка {work}")
    for k in kinds.KINDS.values():
        if k.needs:
            log(f"{k.id}: ⏭️  демо — вместе с {k.needs}")
            continue
        root = work / k.id
        shutil.copytree(KIND_DEMOS / k.id, root)
        log(f"{k.id}:")
        with r.step(f"{k.id}: validate") as st:
            if cli.main(["validate", str(root)]):
                st["errors"].append("validate вернул ошибку")
        if st["errors"]:
            continue
        with r.step(f"{k.id}: voice → render → assemble") as st:
            proj = project.load(root)
            tl = timing.layout(proj, log=_quiet)
            render.render(proj, workers=workers, log=_quiet)
            assemble(proj, log=_quiet)
            st["note"] = f"{proj.cfg['format']}, {tl['duration']:.1f} c, {tl['total_frames']} кадров"
        if st["errors"]:
            continue
        with r.step(f"{k.id}: qa") as st:
            lines = []
            if not qa_run(proj, log=lines.append):
                st["errors"] += [x for x in lines if x.startswith("[FAIL]")]
            st["note"] = "; ".join(x[7:] for x in lines if x.startswith("[PASS] Тип") or "Музыка звучит" in x)
    ok = not r.fails
    if ok and not keep:
        shutil.rmtree(work, ignore_errors=True)
    log(f"{'✅ демо типов прошли QA' if ok else '❌ не прошли: ' + ', '.join(dict.fromkeys(r.fails))} "
        f"за {time.time() - r.t0:.0f} c")
    if not ok or keep:
        log(f"  рабочая папка оставлена: {work}")
    return ok
