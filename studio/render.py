"""Рендер: сцена -> mp4 (кадры идут в ffmpeg через pipe, без PNG на диске).

Кэш: build/render/<chapter>/<scene>.mp4 + .key. Ключ = хэш тайминга сцены + кода + стиля.
Сцены рендерятся параллельно процессами; прерванный рендер продолжается с недоделанных сцен.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image

from . import gfx as G
from . import subs as S
from . import templates as TP
from .project import Project, stable_hash, STUDIO_ROOT, VERSION
from .timing import load_timeline


def code_hash(proj_root=None):
    # только код, который рисует кадр; данные сцены (тексты, тайминги) уже в хэше сцены
    h = hashlib.sha1(b"render")
    files = [STUDIO_ROOT / "studio" / n for n in ("gfx.py", "templates.py", "render.py")]
    if proj_root and (Path(proj_root) / "templates").exists():
        files += sorted((Path(proj_root) / "templates").glob("*.py"))
    for f in files:
        h.update(f.read_bytes())
    return h.hexdigest()[:10]


def prepare(proj: Project):
    """Сцены в глобальном порядке + непрерывное состояние (позиция ленты) на входе каждой сцены."""
    tl = load_timeline(proj)
    G.set_palette(proj.cfg["style"].get("palette", "neon"))
    G.FONT_FAMILY = proj.cfg["style"].get("font", G.FONT_FAMILY)
    TP.load_project_templates(proj.root)
    W, H = tl["size"]
    ctx = {"W": W, "H": H, "fps": tl["fps"]}
    scenes = tl["scenes"]
    state = {"feed_offset": 0.0, "screen_dim": 0.0}
    ch_code = code_hash(proj.root)
    style_key = stable_hash(proj.cfg["style"]) + stable_hash(proj.cfg["subtitles"])
    for i, s in enumerate(scenes):
        s["first"], s["last"] = i == 0, i == len(scenes) - 1
        s["state_in"] = dict(state)
        cls = TP.REGISTRY.get(s["template"])
        if cls is None:
            raise SystemExit(f"Неизвестный шаблон '{s['template']}' в сцене {s['chapter']}/{s['id']}")
        tpl = cls(ctx, s, s["state_in"])
        if tpl.feed_speed:
            off = state["feed_offset"]
            for f in range(s["n_frames"]):
                off += tpl.feed_speed(f / tl["fps"]) / tl["fps"]
            state["feed_offset"] = off
        if tpl.uses_phone:
            state["screen_dim"] = float(tpl.dim_out)
        s["key"] = stable_hash([s["hash"], round(s["state_in"]["feed_offset"], 2), s["state_in"]["screen_dim"], ch_code, style_key,
                                proj.cfg["render"]["crf"], proj.cfg["render"]["preset"], W, H])
    return tl, ctx


# ---------------------------------------------------------------- per-process caches
_BG = {}


def _bg(W, H):
    if (W, H) not in _BG:
        _BG[(W, H)] = G.Background(W, H)
    return _BG[(W, H)]


def _sub_sprite(lines, size, W):
    key = ("sub", tuple(lines), size)
    if key in _BG:
        return _BG[key]
    f = G.font(size, "bold")
    lh = int(size * 1.2)
    tw = int(max(f.getlength(l) for l in lines))
    pw, ph = tw + int(size * 1.1), lh * len(lines) + int(size * 0.62)
    box = G.rrect((pw, ph), int(size * 0.45), (6, 5, 14, 215))
    from PIL import ImageDraw
    d = ImageDraw.Draw(box)
    for i, l in enumerate(lines):
        x = (pw - f.getlength(l)) / 2
        y = int(size * 0.24) + i * lh
        d.text((x + 2, y + 3), l, font=f, fill=(0, 0, 0, 160))
        d.text((x, y), l, font=f, fill=G.col("text"))
    _BG[key] = box
    return box


def draw_subs(img, scene, t, proj_sub_size, W, H):
    for c in scene.get("subs") or []:
        if c["t0"] - 0.02 <= t < c["t1"]:
            a = min(G.prog(t, c["t0"] - 0.02, c["t0"] + 0.08), 1 - G.prog(t, c["t1"] - 0.08, c["t1"]))
            spr = _sub_sprite(tuple(c["lines"]), proj_sub_size, W)
            y = H * (0.835 if H >= W else 0.885)
            G.blitc(img, spr, W / 2, y, max(0.0, a), 0.985 + 0.015 * G.eo(G.prog(t, c["t0"], c["t0"] + 0.12)))


def make_template(ctx, scene):
    tpl = TP.REGISTRY[scene["template"]](ctx, scene, scene["state_in"])
    tpl.setup()
    return tpl


def frame(ctx, tpl, scene, f, sub_size):
    fps = ctx["fps"]
    t = f / fps
    T = (scene["start_frame"] + f) / fps
    img = _bg(ctx["W"], ctx["H"]).frame(T)
    tpl.draw(img, t, T)
    draw_subs(img, scene, t, sub_size, ctx["W"], ctx["H"])
    return img


def _render_scene_job(proj_root, scene, ctx, sub_size, out, crf, preset, palette, font_family):
    G.set_palette(palette)
    G.FONT_FAMILY = font_family
    TP.load_project_templates(proj_root)
    t0 = time.time()
    tpl = make_template(ctx, scene)
    W, H, fps = ctx["W"], ctx["H"], ctx["fps"]
    tmp = str(out) + ".part.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-g", str(fps * 2), "-threads", "1", "-movflags", "+faststart", tmp]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for f in range(scene["n_frames"]):
        img = frame(ctx, tpl, scene, f, sub_size)
        p.stdin.write(img.convert("RGB").tobytes())
    p.stdin.close()
    err = p.stderr.read().decode()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg ({scene['id']}): {err[-400:]}")
    os.replace(tmp, out)
    Path(str(out) + ".key").write_text(scene["key"])
    return scene["id"], scene["n_frames"], time.time() - t0


def scene_out(proj, s):
    return proj.bdir("render", s["chapter"]) / f"{s['id']}.mp4"


def is_fresh(proj, s):
    o = scene_out(proj, s)
    k = Path(str(o) + ".key")
    return o.exists() and k.exists() and k.read_text().strip() == s["key"]


def render(proj: Project, chapter=None, workers=None, log=print, force=False):
    tl, ctx = prepare(proj)
    todo = [s for s in tl["scenes"] if (chapter in (None, s["chapter"])) and (force or not is_fresh(proj, s))]
    if not todo:
        log("Все сцены актуальны — рендерить нечего.")
        return tl
    workers = workers or proj.cfg["render"].get("workers") or max(1, (os.cpu_count() or 2))
    sub_size = S.font_size(proj)
    frames = sum(s["n_frames"] for s in todo)
    log(f"Рендер {len(todo)} сцен, {frames} кадров, процессов: {workers}")
    todo.sort(key=lambda s: -s["n_frames"])
    t0 = time.time()
    done = 0
    args = (proj.cfg["render"]["crf"], proj.cfg["render"]["preset"], proj.cfg["style"].get("palette", "neon"),
            G.FONT_FAMILY)
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_render_scene_job, str(proj.root), s, ctx, sub_size, scene_out(proj, s), *args) for s in todo]
        for fu in as_completed(futs):
            sid, n, dt = fu.result()
            done += n
            el = time.time() - t0
            log(f"  {sid}: {n} кадров за {dt:.0f} c ({n / dt:.1f} fps) | всего {done}/{frames}, "
                f"осталось ~{el / done * (frames - done):.0f} c")
            sys.stdout.flush()
    return tl


def stills(proj: Project, chapter=None, times=None, out_name=None, log=print):
    """Контрольные кадры ДО полного рендера: середины битов + начало/конец сцен -> один лист."""
    tl, ctx = prepare(proj)
    sub_size = S.font_size(proj)
    picks = []
    for s in tl["scenes"]:
        if chapter not in (None, s["chapter"]):
            continue
        ts = [0.12] + [(b["t0"] + b["t1"]) / 2 for b in s["beats"]] + [s["dur"] - 0.1]
        if times:
            ts = [x - s["start"] for x in times if s["start"] <= x < s["start"] + s["dur"]]
        for x in ts:
            picks.append((s, max(0.0, min(s["dur"] - 1 / tl["fps"], x))))
    if not picks:
        raise SystemExit("Нет кадров для листа")
    tpls = {}
    thumbs = []
    W, H = ctx["W"], ctx["H"]
    tw = 300 if H >= W else 420
    th = int(tw * H / W)
    from PIL import ImageDraw
    for s, x in picks:
        key = (s["chapter"], s["id"])
        if key not in tpls:
            tpls[key] = make_template(ctx, s)
        img = frame(ctx, tpls[key], s, int(round(x * tl["fps"])), sub_size).convert("RGB").resize((tw, th), Image.LANCZOS)
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, tw, 26), fill=(0, 0, 0))
        d.text((6, 4), f"{s['chapter']}/{s['id']} t={s['start'] + x:.2f}", font=G.font(16, "semibold"), fill=(255, 255, 0))
        thumbs.append(img)
    cols = 6 if H >= W else 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + 4), rows * (th + 4)), (40, 40, 40))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * (tw + 4), (i // cols) * (th + 4)))
    out = proj.qa_dir / (out_name or f"stills_{chapter or 'all'}.png")
    sheet.save(out)
    log(f"Лист кадров: {out} ({len(thumbs)} кадров)")
    return out


def frame_png(proj, t_global, out):
    tl, ctx = prepare(proj)
    for s in tl["scenes"]:
        if s["start"] <= t_global < s["start"] + s["dur"]:
            img = frame(ctx, make_template(ctx, s), s, int(round((t_global - s["start"]) * tl["fps"])), S.font_size(proj))
            img.convert("RGB").save(out)
            return out
    raise SystemExit("Время вне ролика")
