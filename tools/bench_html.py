"""Замеры второго движка (ROADMAP C6): PIL против HTML (web.html, headless Chromium) на фикстуре tests/fixtures/web.

  python tools/bench_html.py [--frames 60] [--workers N]

1. Кадр/с по сценам (1 процесс, без кодирования): statement (PIL) и web.html, чистовой и черновой размер;
   у web.html — разбивка: seek (JS), снимок (CDP PNG), декодирование и наложение.
2. Способ снимка: CDP captureScreenshot c optimizeForSpeed / без / page.screenshot(omit_background).
3. Детерминизм: кадры по одному на свежей странице против подряд (как кусками и в разных процессах) и два
   полных рендера сцены — framemd5 ffmpeg.
4. Рендер + assemble всего ролика (куски, процессы, `concat -c copy`): время, параметры потоков сцен, кадров в
   финале = кадров в timeline.

Офлайн, голос fake, денег не тратит; рабочая папка — временная.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402

from studio import assemble, project, render, timing  # noqa: E402
from studio.packs.web import browser as B  # noqa: E402
from studio.selftest import pin_fonts  # noqa: E402

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "web"


def _scene(tl, sid):
    return next(s for s in tl["scenes"] if s["id"] == sid)


def fps_of(proj, sid, frames, draft):
    tl, ctx = render.prepare(proj, draft)
    s = _scene(tl, sid)
    tpl = render.make_template(ctx, s)
    sub = render.sub_size(proj, ctx)
    n = min(frames, s["n_frames"])
    render.frame(ctx, tpl, s, 0, sub)  # прогрев: страница, шрифты, спрайты
    t0 = time.perf_counter()
    for f in range(n):
        render.frame(ctx, tpl, s, f, sub).convert("RGB").tobytes()
    return n / (time.perf_counter() - t0), ctx, tpl, s


def html_phases(tpl, s, frames):
    pg = B.page(tpl.key, tpl.file, tpl.W, tpl.H, tpl.scene, tpl.css)
    acc = {"seek": 0.0, "png": 0.0, "decode": 0.0}
    n = min(frames, s["n_frames"])
    for f in range(n):
        c0 = time.perf_counter()
        pg.evaluate(B.SEEK_JS, f / tpl.fps)
        c1 = time.perf_counter()
        r = pg._studio_cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
        c2 = time.perf_counter()
        Image.open(io.BytesIO(base64.b64decode(r["data"]))).convert("RGBA")
        c3 = time.perf_counter()
        acc["seek"] += c1 - c0
        acc["png"] += c2 - c1
        acc["decode"] += c3 - c2
    return {k: v / n * 1000 for k, v in acc.items()}


def capture_modes(tpl, frames):
    pg = B.page(tpl.key, tpl.file, tpl.W, tpl.H, tpl.scene, tpl.css)
    pg.evaluate(B.SEEK_JS, 2.0)
    modes = {
        "CDP png, optimizeForSpeed": lambda: pg._studio_cdp.send("Page.captureScreenshot",
                                                                  {"format": "png", "optimizeForSpeed": True}),
        "CDP png": lambda: pg._studio_cdp.send("Page.captureScreenshot", {"format": "png"}),
        "page.screenshot(omit_background)": lambda: pg.screenshot(omit_background=True),
    }
    out = {}
    for name, fn in modes.items():
        fn()
        t0 = time.perf_counter()
        for _ in range(frames):
            fn()
        out[name] = (time.perf_counter() - t0) / frames * 1000
    return out


def _pm(img):
    """Премультиплицированный RGBA: цвет почти прозрачных пикселей (альфа 1–2) — шум растра, на кадр не влияет."""
    import numpy as np
    a = np.asarray(img).astype(np.int32)
    return np.concatenate([a[..., :3] * a[..., 3:] // 255, a[..., 3:]], -1)


def determinism(tpl, s):
    """Кадры подряд на одной странице против каждого на свежем браузере (как первый кадр куска в другом процессе):
    (сравнено кадров, точных совпадений, наибольшая разница премультиплицированного RGBA)."""
    import numpy as np
    fs = [0, 7, s["n_frames"] // 3, s["n_frames"] // 2, s["n_frames"] - 1]
    seq = {}
    for f in range(s["n_frames"]):  # все кадры подряд, как в рендере; храним только сравниваемые
        img = tpl.layer(f / tpl.fps)
        if f in fs:
            seq[f] = _pm(img)
    same, worst = 0, 0
    for f in fs:
        B.close()  # новый браузер и страница: прошлое состояние не помогает
        d = int(np.abs(_pm(tpl.layer(f / tpl.fps)) - seq[f]).max())
        same += d == 0
        worst = max(worst, d)
    return len(fs), same, worst


def framemd5(p):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-map", "0:v", "-f", "framemd5", "-"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return [l.rsplit(",", 1)[-1].strip() for l in r.stdout.splitlines() if not l.startswith("#")]


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=codec_name,profile,pix_fmt,width,height,r_frame_rate,time_base,nb_read_frames",
                        "-of", "json", str(p)], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    return json.loads(r.stdout)["streams"][0]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--workers", type=int, default=None)
    a = ap.parse_args(argv)
    pin_fonts()
    tmp = Path(tempfile.mkdtemp(prefix="bench-html-"))
    try:
        shutil.copytree(FIXTURE, tmp / "web")
        proj = project.load(tmp / "web")
        timing.layout(proj, log=lambda *_: None)
        proj = project.load(tmp / "web")
        print("## 1. Кадр/с, 1 процесс, без кодирования (фон + сцена + субтитры)\n")
        print("| сцена | движок | кадр | кадр/с | мс/кадр |\n|---|---|---|---|---|")
        res = {}
        for sid, eng in (("s01", "PIL (statement)"), ("s02", "HTML (web.html)")):
            for draft in (False, True):
                v, ctx, tpl, s = fps_of(proj, sid, a.frames, draft)
                res[(sid, draft)] = (v, tpl, s)
                print(f"| {sid} | {eng} | {ctx['W']}×{ctx['H']} | {v:.1f} | {1000 / v:.1f} |")
        _, tpl, s = res[("s02", False)]
        print("\n## 2. Кадр web.html по фазам, мс (1080×1920)\n")
        print(" | ".join(f"{k} {v:.1f}" for k, v in html_phases(tpl, s, a.frames).items()))
        print("\n## 3. Способ снимка, мс/кадр (1080×1920)\n")
        for k, v in capture_modes(tpl, 20).items():
            print(f"- {k}: {v:.1f}")
        B.close()  # page.screenshot(omit_background) после снимка возвращает странице белый фон
        n, same, worst = determinism(tpl, s)
        print(f"\n## 4. Детерминизм\n\n- кадр на свежем браузере = кадр подряд: {same}/{n} точно, наибольшая разница "
              f"{worst}/255 (премультиплицированный RGBA)")
        B.close()
        times = {}
        for i in (1, 2):
            t0 = time.perf_counter()
            render.render(proj, workers=a.workers, force=True, log=lambda *_: None)
            times[i] = time.perf_counter() - t0
            md5 = framemd5(render.scene_out(proj, _scene(render.prepare(proj)[0], "s02")))
            if i == 1:
                first = md5
        print(f"- два полных рендера сцены web.html, framemd5: {'совпали' if md5 == first else 'РАЗНЫЕ'} "
              f"({len(md5)} кадров)")
        print(f"\n## 5. Рендер ролика ({sum(s['n_frames'] for s in render.prepare(proj)[0]['scenes'])} кадров, "
              f"процессов: {a.workers or render.default_workers()}): {times[1]:.1f} c, повтор {times[2]:.1f} c\n")
        tl, _ = render.prepare(proj)
        keys = ("codec_name", "profile", "pix_fmt", "width", "height", "r_frame_rate", "time_base")
        streams = {s["id"]: probe(render.scene_out(proj, s)) for s in tl["scenes"]}
        for sid, st in streams.items():
            print(f"- {sid}: " + ", ".join(str(st[k]) for k in keys) + f", кадров {st['nb_read_frames']}")
        same = len({tuple(st[k] for k in keys) for st in streams.values()}) == 1
        t0 = time.perf_counter()
        final = assemble.assemble(proj, log=lambda *_: None)
        fin = probe(final)
        want = sum(s["n_frames"] for s in tl["scenes"])
        print(f"- параметры потоков сцен одинаковые: {'да' if same else 'НЕТ'}; assemble (concat -c copy) "
              f"{time.perf_counter() - t0:.1f} c, кадров в финале {fin['nb_read_frames']} из {want}")
    finally:
        B.close()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
