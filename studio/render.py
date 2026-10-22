"""Рендер: сцена -> mp4 (кадры идут в ffmpeg через pipe, без PNG на диске).

Кэш: build/render/<chapter>/<scene>.mp4 + .key. Ключ = хэш тайминга сцены + кода её шаблона (`codehash`) + стиля.
Сцены рендерятся параллельно процессами; прерванный рендер продолжается с недоделанных сцен.
"""
from __future__ import annotations

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
from . import packs as TP
from .codehash import code_hash, scene_code_hash  # noqa: F401  — code_hash: прежнее имя
from .project import Project, stable_hash, STUDIO_ROOT, VERSION
from .timing import load_timeline


def prepare(proj: Project):
    """Сцены в глобальном порядке + непрерывное состояние (позиция ленты) на входе каждой сцены."""
    tl = load_timeline(proj)
    style = G.apply_style(proj.cfg["style"])
    TP.load_project_templates(proj.root)
    W, H = tl["size"]
    ctx = {"W": W, "H": H, "fps": tl["fps"], "language": proj.cfg["language"], "style": style}
    scenes = tl["scenes"]
    state = {"feed_offset": 0.0, "screen_dim": 0.0}
    # подсветки фона по главам (glow в script/chNN.yaml): цвет на стыке переносится через state
    glows = {ch: G.chapter_glow(d.get("glow"), style) for ch, d in proj.chapters}
    base_glow = (style.pal["glow_cool"], style.pal["glow_warm"])
    use_glow = style.background == "lab" and any(glows.values())
    if use_glow and scenes:
        state["lab_glow"] = glows.get(scenes[0]["chapter"]) or base_glow  # начало ролика — без перехода
    codes = {}  # класс шаблона → хэш кода, который рисует его сцены
    style_key = stable_hash([proj.cfg["style"], proj.cfg["subtitles"], proj.cfg["language"]])
    for i, s in enumerate(scenes):
        s["first"], s["last"] = i == 0, i == len(scenes) - 1
        s["state_in"] = dict(state)
        if use_glow:
            s["glow"] = {"from": state["lab_glow"], "to": glows.get(s["chapter"]) or base_glow}
            state["lab_glow"] = s["glow"]["to"]
        cls = TP.REGISTRY.get(s["template"])
        if cls is None:
            raise SystemExit(f"Неизвестный шаблон '{s['template']}' в сцене {s['chapter']}/{s['id']}")
        if cls not in codes:
            codes[cls] = scene_code_hash(cls, proj.root)
        tpl = cls(ctx, s, s["state_in"])
        if tpl.feed_speed:
            off = state["feed_offset"]
            for f in range(s["n_frames"]):
                off += tpl.feed_speed(f / tl["fps"]) / tl["fps"]
            state["feed_offset"] = off
        if tpl.uses_phone:
            state["screen_dim"] = float(tpl.dim_out)
        if hasattr(tpl, "state_out"):  # шаблоны lab: шапка, часы, перенос цифры через склейку
            state.update(tpl.state_out())
        extra = {k: v for k, v in s["state_in"].items() if k not in ("feed_offset", "screen_dim")}
        s["key"] = stable_hash([s["hash"], round(s["state_in"]["feed_offset"], 2), s["state_in"]["screen_dim"], codes[cls], style_key,
                                proj.cfg["render"]["crf"], proj.cfg["render"]["preset"], W, H] + ([extra] if extra else [])
                               + ([s["glow"]] if use_glow else []))
    return tl, ctx


# ---------------------------------------------------------------- per-process caches
_BG = {}
GLOW_T = 1.2  # с: переход подсветок на стыке глав (в начале первой сцены новой главы)


def glow_at(scene, t):
    """Цвета подсветок (cool, warm) в момент t сцены или None, если подсветки по главам не заданы."""
    g = scene.get("glow")
    if not g:
        return None
    k = G.eio(G.prog(t, 0.0, min(GLOW_T, scene["dur"])))
    return tuple(tuple(G.lerp(a, b, k) for a, b in zip(A, B)) for A, B in zip(g["from"], g["to"]))


def _bg(W, H, style=None):
    style = style or G.SM.active()
    key = (W, H, style)
    if key not in _BG:
        if style.background == "lab":
            from .packs.lab.background import LabBackground
            _BG[key] = LabBackground(W, H, style=style)
        else:
            _BG[key] = G.Background(W, H, style=style)
    return _BG[key]


def _sub_sprite(lines, size, W, style):
    key = ("sub", tuple(lines), size, style)
    if key in _BG:
        return _BG[key]
    f = G.font(size, "bold", style=style)
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
        d.text((x, y), l, font=f, fill=style.col("text"))
    _BG[key] = box
    return box


def _karaoke_sprite(lines, n_on, size, style):
    """Субтитры lab: плашка, слова загораются по мере произнесения (неспетые — 38 %)."""
    key = ("kar", tuple(lines), n_on, size, style)
    if key in _BG:
        return _BG[key]
    f = G.font(size, "bold", style=style)
    lh = int(size * 1.25)
    sp = f.getlength(" ") + size * 0.14
    widths = [sum(f.getlength(w) for w in l.split()) + sp * (len(l.split()) - 1) for l in lines]
    pw, ph = int(max(widths) + size * 1.2), lh * len(lines) + int(size * 0.45)
    box = G.rrect((pw, ph), int(size * 0.34), (5, 7, 11, 158))
    from PIL import ImageDraw
    d = ImageDraw.Draw(box)
    i = 0
    for li, l in enumerate(lines):
        x = (pw - widths[li]) / 2
        y = int(size * 0.18) + li * lh
        for w in l.split():
            d.text((x, y), w, font=f, fill=style.col("text", 255 if i < n_on else 97))
            x += f.getlength(w) + sp
            i += 1
    _BG[key] = box
    return box


def draw_subs(img, scene, t, proj_sub_size, W, H, style=None):
    style = style or G.SM.active()
    if style.subs == "karaoke" and scene.get("words"):
        return _draw_karaoke(img, scene, t, proj_sub_size, W, H, style)
    for c in scene.get("subs") or []:
        if c["t0"] - 0.02 <= t < c["t1"]:
            a = min(G.prog(t, c["t0"] - 0.02, c["t0"] + 0.08), 1 - G.prog(t, c["t1"] - 0.08, c["t1"]))
            spr = _sub_sprite(tuple(c["lines"]), proj_sub_size, W, style)
            y = H * (0.835 if H >= W else 0.885)
            G.blitc(img, spr, W / 2, y, max(0.0, a), 0.985 + 0.015 * G.eo(G.prog(t, c["t0"], c["t0"] + 0.12)))


def _draw_karaoke(img, scene, t, size, W, H, style):
    words = scene["words"]
    for c in scene.get("subs") or []:
        if c["t0"] - 0.02 <= t < c["t1"]:
            a = min(G.prog(t, c["t0"] - 0.02, c["t0"] + 0.08), 1 - G.prog(t, c["t1"] - 0.08, c["t1"]))
            n_all = sum(len(l.split()) for l in c["lines"])
            inside = [w for w in words if c["t0"] - 0.05 <= w["t0"] < c["t1"]]
            n_on = sum(1 for w in inside if w["t0"] <= t)
            if len(inside) != n_all:  # таймкоды не совпали с нарезкой — равномерно по времени фрагмента
                n_on = int(n_all * G.prog(t, c["t0"], c["t1"] - 0.3) + 0.999)
            spr = _karaoke_sprite(tuple(c["lines"]), min(n_all, n_on), size, style)
            z = min(W, H) / 1080
            cy = H * 0.835 if H >= W else H - 24 * z - spr.height / 2  # горизонталь: низ плашки в 24 px от края (демо)
            G.blitc(img, spr, W / 2, cy, max(0.0, a))


def make_template(ctx, scene):
    tpl = TP.REGISTRY[scene["template"]](ctx, scene, scene["state_in"])
    tpl.setup()
    return tpl


def frame(ctx, tpl, scene, f, sub_size):
    fps = ctx["fps"]
    t = f / fps
    T = (scene["start_frame"] + f) / fps
    style = ctx["style"]
    glow = glow_at(scene, t)
    bg = _bg(ctx["W"], ctx["H"], style)
    img = bg.frame(T, glow) if glow else bg.frame(T)
    if getattr(tpl, "camera", False) and style.camera:
        from .packs.lab.background import composite_camera
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        tpl.draw(layer, t, T)
        composite_camera(img, layer, T)
    else:
        tpl.draw(img, t, T)
    draw_subs(img, scene, t, sub_size, ctx["W"], ctx["H"], style)
    return img


def _render_scene_job(proj_root, scene, ctx, sub_size, out, crf, preset):
    G.apply_style(ctx["style"])  # активный — для хелперов gfx без style= (шаблоны проектов)
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
    args = (proj.cfg["render"]["crf"], proj.cfg["render"]["preset"])
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
