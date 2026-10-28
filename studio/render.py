"""Рендер: сцена -> mp4 (кадры идут в ffmpeg через pipe, без PNG на диске).

Кэш: build/render/<chapter>/<scene>.mp4 + .key. Ключ = хэш тайминга сцены + кода её шаблона (`codehash`) + стиля.
Сцены рендерятся параллельно процессами; длинная сцена — кусками по ~CHUNK кадров (build/render/<chapter>/parts/,
каждый кусок — свой mp4 с ключевым кадром в начале), куски склеиваются `concat` без перекодирования (P3.3).
Прерванный рендер продолжается с недоделанных сцен и кусков.
Черновик (`render --draft`, P3.4): половина разрешения, x264 `ultrafast`, свой кэш build/render-draft/ — чистовой
кэш не трогает. Шаблоны рисуют в долях W/H (self.u, self.z), поэтому на полразмера кадр тот же, только мельче.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw

from . import assets as AS
from . import gfx as G
from . import imagegen as IG
from . import subs as S
from . import packs as TP
from . import platforms as PL
from .codehash import code_hash, scene_code_hash  # noqa: F401  — code_hash: прежнее имя
from .project import Project, stable_hash, STUDIO_ROOT, VERSION
from .timing import load_timeline


DRAFT_PRESET = "ultrafast"
_ONCE = None  # {ключ входов: (tl, ctx)} внутри prepare_once(), иначе None


@contextlib.contextmanager
def prepare_once():
    """Внутри одной команды код не меняется: prepare() считается один раз на (проект, draft, входы) (P3.5).
    Иначе assemble (+ sfx), stills (+ поля qa), all (render → assemble → qa) повторяют его — хэш кода шаблонов
    там 85 % цены. CLI оборачивает так каждую команду; вне scope — каждый вызов заново (тесты правят код)."""
    global _ONCE
    outer = _ONCE
    if outer is None:
        _ONCE = {}
    try:
        yield
    finally:
        if outer is None:
            _ONCE = None


def prepare(proj: Project, draft=False):
    """Сцены в глобальном порядке + непрерывное состояние (позиция ленты) на входе каждой сцены.
    draft — черновик: кадр вдвое меньше (стороны чётные — для yuv420p), сцены пишутся в build/render-draft/.
    Внутри prepare_once() — из кэша (копия: вызывающий может её менять)."""
    if _ONCE is None:
        return _prepare(proj, draft)
    tlp = proj.build / "timeline.json"
    st = tlp.stat() if tlp.exists() else None
    key = stable_hash([str(proj.root.resolve()), draft, proj.cfg, proj.chapters,
                       st and (st.st_mtime_ns, st.st_size)])
    if key not in _ONCE:
        _ONCE[key] = _prepare(proj, draft)
        return copy.deepcopy(_ONCE[key][0]), dict(_ONCE[key][1])
    # стиль и шаблоны проекта — глобальные: между вызовами их мог сменить другой проект
    style = G.apply_style(proj.cfg["style"])
    TP.load_project_templates(proj.root)
    tl, ctx = _ONCE[key]
    return copy.deepcopy(tl), dict(ctx, style=style)


def _prepare(proj: Project, draft=False):
    tl = load_timeline(proj)
    style = G.apply_style(proj.cfg["style"])
    TP.load_project_templates(proj.root)
    W, H = tl["size"]
    if draft:
        W, H = W // 4 * 2, H // 4 * 2
    preset = DRAFT_PRESET if draft else proj.cfg["render"]["preset"]
    ctx = {"W": W, "H": H, "fps": tl["fps"], "language": proj.cfg["language"], "style": style, "preset": preset,
           "safe": PL.layout_zone(proj.cfg), "subs_top": S.band_top(proj),  # сетка вёрстки: Template.safe/area (B2)
           "subs_bottom": S.bottom_limit(proj),  # субтитры над нижним полем зоны площадки (B3)
           "roots": [str(r) for r in AS.roots(proj)]}  # ассеты сцен (assets/…) — от папки проекта (ROADMAP C2)
    scenes = tl["scenes"]
    state = {"feed_offset": 0.0, "screen_dim": 0.0}
    # подсветки фона по главам (glow в script/chNN.yaml): цвет на стыке переносится через state
    glows = {ch: G.chapter_glow(d.get("glow"), style) for ch, d in proj.chapters}
    base_glow = (style.pal["glow_cool"], style.pal["glow_warm"])
    use_glow = style.background == "lab" and any(glows.values())
    if use_glow and scenes:
        state["lab_glow"] = glows.get(scenes[0]["chapter"]) or base_glow  # начало ролика — без перехода
    codes = {}  # класс шаблона → хэш кода, который рисует его сцены
    scripts = {(ch, sc.get("id")): sc for ch, d in proj.chapters for sc in d.get("scenes") or []}
    style_key = stable_hash([proj.cfg["style"], proj.cfg["subtitles"], proj.cfg["language"]])
    wipe = style.motion.get("transition") == "wipe"
    for i, s in enumerate(scenes):
        s["first"], s["last"] = i == 0, i == len(scenes) - 1
        s["state_in"] = dict(state)
        s["render_dir"] = "render-draft" if draft else "render"
        if use_glow:
            s["glow"] = {"from": state["lab_glow"], "to": glows.get(s["chapter"]) or base_glow}
            state["lab_glow"] = s["glow"]["to"]
        auto = _image_params(proj, scripts, s)  # сцена с image: → params шаблона image (ROADMAP C5.5)
        if auto:
            s["params"] = {**auto, **s["params"]}
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
        media = AS.fingerprint(AS.roots(proj), s["params"])  # содержимое фото и видео сцены: заменили файл — перерисовать
        s["key"] = stable_hash([s["hash"], round(s["state_in"]["feed_offset"], 2), s["state_in"]["screen_dim"], codes[cls], style_key,
                                proj.cfg["render"]["crf"], preset, W, H, ctx["safe"], ctx["subs_top"]] + ([extra] if extra else [])
                               + ([ctx["subs_bottom"]] if ctx["subs_bottom"] is not None else [])
                               + ([s["glow"]] if use_glow else []) + ([media] if media else [])
                               + ([auto] if auto else [])
                               + ([s["first"], s["last"]] if wipe else []))  # шторка зависит от места сцены
    return tl, ctx


def _image_params(proj, scripts, s):
    """params из картинок сцены (imagegen.scene_params) — только по готовым PNG; нет файла — стоп с подсказкой."""
    sc = scripts.get((s["chapter"], s["id"]))
    if not sc or not sc.get("image") or getattr(TP.REGISTRY.get(s["template"]), "NAME", None) != IG.TEMPLATE:
        return {}  # картинка для своего шаблона сцены — его params, не наши
    auto, need = IG.scene_params(proj, s["chapter"], sc, len(s.get("beats") or []))
    if need:
        raise SystemExit(f"Сцена {s['chapter']}/{s['id']}: нет картинок {', '.join(need[:3])}"
                         f"{' …' if len(need) > 3 else ''} — сначала: python -m studio images {proj.slug}")
    return auto


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
        elif style.background == "solid":
            _BG[key] = G.SolidBackground(W, H, style=style)
        elif style.background == "image":
            from .brand import path
            b = style.brand["background"]
            _BG[key] = G.PhotoBackground(W, H, path(b["file"]), b.get("dim", 0.45), style=style)
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


def _tiktok_sprite(lines, n_on, size, style):
    """Крупные TikTok-субтитры (бренд-кит, subs: tiktok): без плашки, жирный текст с обводкой, слово,
    которое звучит, — акцентом."""
    key = ("tik", tuple(lines), n_on, size, style)
    if key in _BG:
        return _BG[key]
    f = G.font(size, "bold", style=style)  # тот же вес, что у переноса строк (subs.chunks_for_scene)
    sw = max(2, int(size * 0.09))
    lh = int(size * 1.18)
    sp = f.getlength(" ")
    widths = [sum(f.getlength(w) for w in l.split()) + sp * (len(l.split()) - 1) for l in lines]
    pw, ph = int(max(widths) + 4 * sw), lh * len(lines) + 4 * sw
    box = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    from PIL import ImageDraw
    d = ImageDraw.Draw(box)
    i = 0
    for li, l in enumerate(lines):
        x = (pw - widths[li]) / 2
        y = 2 * sw + li * lh
        for w in l.split():
            c = style.col("accent") if i == n_on - 1 else style.col("text")
            d.text((x, y), w, font=f, fill=c, stroke_width=sw, stroke_fill=(0, 0, 0, 235))
            x += f.getlength(w) + sp
            i += 1
    _BG[key] = box
    return box


def draw_subs(img, scene, t, proj_sub_size, W, H, style=None, bottom=None):
    """bottom — низ субтитров не ниже этой доли H (зона площадки, subs.bottom_limit); None — место по формату."""
    style = style or G.SM.active()
    if style.subs in ("karaoke", "tiktok") and scene.get("words"):
        return _draw_karaoke(img, scene, t, proj_sub_size, W, H, style, bottom)
    for c in scene.get("subs") or []:
        if c["t0"] - 0.02 <= t < c["t1"]:
            a = min(G.prog(t, c["t0"] - 0.02, c["t0"] + 0.08), 1 - G.prog(t, c["t1"] - 0.08, c["t1"]))
            spr = _sub_sprite(tuple(c["lines"]), proj_sub_size, W, style)
            y = S.place(H * (0.835 if H >= W else 0.885), spr.height, H, bottom)
            G.blitc(img, spr, W / 2, y, max(0.0, a), 0.985 + 0.015 * G.eo(G.prog(t, c["t0"], c["t0"] + 0.12)))


def _draw_karaoke(img, scene, t, size, W, H, style, bottom=None):
    words = scene["words"]
    for c in scene.get("subs") or []:
        if c["t0"] - 0.02 <= t < c["t1"]:
            a = min(G.prog(t, c["t0"] - 0.02, c["t0"] + 0.08), 1 - G.prog(t, c["t1"] - 0.08, c["t1"]))
            n_all = sum(len(l.split()) for l in c["lines"])
            inside = [w for w in words if c["t0"] - 0.05 <= w["t0"] < c["t1"]]
            n_on = sum(1 for w in inside if w["t0"] <= t)
            if len(inside) != n_all:  # таймкоды не совпали с нарезкой — равномерно по времени фрагмента
                n_on = int(n_all * G.prog(t, c["t0"], c["t1"] - 0.3) + 0.999)
            z = min(W, H) / 1080
            if style.subs == "tiktok":  # крупно и выше интерфейса площадки (правая колонка и низ у TikTok/Reels)
                spr = _tiktok_sprite(tuple(c["lines"]), min(n_all, n_on), size, style)
                G.blitc(img, spr, W / 2, S.place(H * (0.66 if H >= W else 0.80), spr.height, H, bottom), max(0.0, a))
                continue
            spr = _karaoke_sprite(tuple(c["lines"]), min(n_all, n_on), size, style)
            cy = H * 0.835 if H >= W else H - 24 * z - spr.height / 2  # горизонталь: низ плашки в 24 px от края (демо)
            G.blitc(img, spr, W / 2, S.place(cy, spr.height, H, bottom), max(0.0, a))


def make_template(ctx, scene):
    tpl = TP.REGISTRY[scene["template"]](ctx, scene, scene["state_in"])
    tpl.setup()
    return tpl


def frame(ctx, tpl, scene, f, sub_size, alpha=False):
    """Кадр f сцены. alpha — без фона и субтитров, на прозрачном (экспорт для монтажки, `export_alpha`)."""
    fps = ctx["fps"]
    t = f / fps
    T = (scene["start_frame"] + f) / fps
    style = ctx["style"]
    if alpha:
        img = Image.new("RGBA", (ctx["W"], ctx["H"]), (0, 0, 0, 0))
    else:
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
    if not alpha:
        if not getattr(tpl, "speech_on_screen", False):  # kit.kinetic: текст в кадре и есть речь
            draw_subs(img, scene, t, sub_size, ctx["W"], ctx["H"], style, ctx.get("subs_bottom"))
        if style.motion.get("transition") == "wipe":
            draw_wipe(img, scene, t, style)
    return img


WIPE = 0.2  # с: шторка закрывает кадр в конце сцены и столько же открывает в начале следующей


def draw_wipe(img, scene, t, style):
    """Шторка бренд-кита между сценами (motion.transition: wipe). В конце сцены косая панель цвета фона с полосой
    акцента наезжает справа и закрывает кадр, в начале следующей — уезжает влево. На склейке кадр с обеих сторон
    закрыт одним цветом, поэтому шва не видно, а сцены по-прежнему рендерятся и кэшируются по отдельности.
    Начало ролика и конец последней сцены — без шторки; сцены короче 4·WIPE — тоже (мелькало бы)."""
    D = scene["dur"]
    if D < 4 * WIPE:
        return
    W, H = img.size
    sl, bar = W * 0.22, W * 0.06  # наклон кромки и ширина полосы акцента
    if not scene.get("last") and t > D - WIPE:
        e = G.lerp(W + bar, -sl - 2, G.eio(G.prog(t, D - WIPE, D)))  # 2 px запаса: кромка полигона включительна
        panel = [(e + sl, 0), (W + sl, 0), (W + sl, H), (e, H)]
        stripe = [(e + sl - bar, 0), (e + sl, 0), (e, H), (e - bar, H)]
    elif not scene.get("first") and t < WIPE:
        e = G.lerp(W + 2, -sl - bar, G.eio(G.prog(t, 0, WIPE)))
        panel = [(-sl, 0), (e + sl, 0), (e, H), (-sl, H)]
        stripe = [(e + sl, 0), (e + sl + bar, 0), (e + bar, H), (e, H)]
    else:
        return
    d = ImageDraw.Draw(img)
    d.polygon(panel, fill=style.col("bg_bot"))
    d.polygon(stripe, fill=style.col("accent"))


ALPHA = {  # прозрачный экспорт для монтажки (ROADMAP C2, старый R4): кодек и пиксельный формат с альфой
    "mov": ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-vendor", "apl0"],  # ProRes 4444
    "webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", "30", "-row-mt", "1",
             "-auto-alt-ref", "0"],
}


def export_alpha(proj: Project, fmt="mov", chapter=None, log=print):
    """Графика ролика без фона и субтитров на прозрачном → build/final/<slug>[.<глава>].alpha.<mov|webm> (без звука):
    слой поверх своего видео в монтажке. Без кэша — одним проходом по сценам."""
    if fmt not in ALPHA:
        raise SystemExit(f"--alpha: {fmt}? Есть: {', '.join(ALPHA)}")
    tl, ctx = prepare(proj)
    scenes = [s for s in tl["scenes"] if chapter in (None, s["chapter"])]
    if not scenes:
        raise SystemExit(f"Нет сцен главы {chapter}")
    W, H, fps = ctx["W"], ctx["H"], ctx["fps"]
    out = proj.bdir("final") / f"{proj.slug}{'.' + chapter if chapter else ''}.alpha.{fmt}"
    tmp = out.with_name(out.stem + ".part." + fmt)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(fps),
           "-i", "-", *ALPHA[fmt], "-an", str(tmp)]
    n = sum(s["n_frames"] for s in scenes)
    log(f"Прозрачный экспорт {fmt} {W}×{H}: {len(scenes)} сцен, {n} кадров")
    t0 = time.time()
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for s in scenes:
            tpl = make_template(ctx, s)
            for f in range(s["n_frames"]):
                p.stdin.write(frame(ctx, tpl, s, f, 0, alpha=True).tobytes())
        p.stdin.close()
    except BrokenPipeError:
        pass
    err = p.stderr.read().decode(errors="replace")
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg (alpha {fmt}): {err[-400:]}")
    os.replace(tmp, out)
    log(f"Готово: {out} ({time.time() - t0:.0f} c)")
    return out


def _render_scene_job(proj_root, scene, ctx, sub_size, out, crf, preset, f0, f1, key):
    """Кадры [f0, f1) сцены → out (mp4, первый кадр — ключевой) + out.key."""
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
    for f in range(f0, f1):
        img = frame(ctx, tpl, scene, f, sub_size)
        p.stdin.write(img.convert("RGB").tobytes())
    p.stdin.close()
    err = p.stderr.read().decode()
    if p.wait() != 0:
        raise RuntimeError(f"ffmpeg ({scene['id']}): {err[-400:]}")
    os.replace(tmp, out)
    Path(str(out) + ".key").write_text(key)
    return scene["id"], f1 - f0, time.time() - t0


CHUNK = 120  # кадров (4 с при 30 fps): кусок длинной сцены — нет одинокого «хвоста» в конце рендера (P3.3)


def chunks(n, size=None):
    """Границы кусков [f0, f1) сцены из n кадров: поровну, около size кадров; короче 1,5 size — один кусок."""
    k = max(1, round(n / (size or CHUNK)))
    return [(n * i // k, n * (i + 1) // k) for i in range(k)]


def sub_size(proj, ctx):
    """Кегль субтитров под размер кадра ctx (у черновика вдвое меньше)."""
    return S.font_size(proj) * ctx["W"] // proj.size[0]


def scene_out(proj, s):
    return proj.bdir(s.get("render_dir", "render"), s["chapter"]) / f"{s['id']}.mp4"


def parts_dir(proj, s):
    return proj.bdir(s.get("render_dir", "render"), s["chapter"], "parts")


def part_out(proj, s, f0, f1):
    return parts_dir(proj, s) / f"{s['id']}.{f0:05d}-{f1:05d}.mp4"


def part_key(s, f0, f1):
    return f"{s['key']}:{f0}-{f1}"


def _fresh(out, key):
    k = Path(str(out) + ".key")
    return out.exists() and k.exists() and k.read_text().strip() == key


def is_fresh(proj, s):
    return _fresh(scene_out(proj, s), s["key"])


def join_parts(parts, out):
    """Куски сцены → один mp4 без перекодирования (параметры кодека у кусков одинаковые)."""
    lst = Path(str(out) + ".txt")
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    tmp = str(out) + ".part.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        "-movflags", "+faststart", tmp], capture_output=True, stdin=subprocess.DEVNULL)
    lst.unlink()
    if r.returncode:
        raise RuntimeError(f"ffmpeg concat ({out.name}): {r.stderr.decode(errors='replace')[-400:]}")
    os.replace(tmp, out)


def _finish_scene(proj, s):
    parts = [part_out(proj, s, f0, f1) for f0, f1 in chunks(s["n_frames"])]
    out = scene_out(proj, s)
    join_parts(parts, out)
    Path(str(out) + ".key").write_text(s["key"])
    for p in parts_dir(proj, s).glob(f"{s['id']}.*"):  # и куски прежних ключей/границ
        p.unlink()


def default_workers():
    """Половина логических ядер: у каждого процесса свой ffmpeg (x264 ≈ столько же CPU, сколько рисование кадра).
    Замер P3.3 (i7-13700, 24 потока): 6 → 195 с, 8 → 166, 12 → 159, 16 → 164, 24 → 185."""
    return max(1, (os.cpu_count() or 2) // 2)


def render_scenes(proj: Project, todo, ctx, workers, log=print, force=False):
    """Сцены todo → build/render. Длинные — кусками; workers=0 — в этом процессе (тесты)."""
    sub_px = sub_size(proj, ctx)
    args = (proj.cfg["render"]["crf"], ctx.get("preset") or proj.cfg["render"]["preset"])
    jobs, left = [], {}  # (сцена, out, f0, f1, ключ); сцена → сколько её кусков ещё рендерится
    for s in sorted(todo, key=lambda s: -s["n_frames"]):
        bounds = chunks(s["n_frames"])
        if len(bounds) == 1:
            jobs.append((s, scene_out(proj, s), 0, s["n_frames"], s["key"]))
            continue
        need = [(f0, f1) for f0, f1 in bounds if force or not _fresh(part_out(proj, s, f0, f1), part_key(s, f0, f1))]
        jobs += [(s, part_out(proj, s, f0, f1), f0, f1, part_key(s, f0, f1)) for f0, f1 in need]
        left[id(s)] = len(need)
        if not need:
            _finish_scene(proj, s)
    frames = sum(f1 - f0 for _, _, f0, f1, _ in jobs)
    t0, done = time.time(), 0

    def finished(s, f0, f1, n, dt):
        nonlocal done
        done += n
        if id(s) in left:
            left[id(s)] -= 1
            if not left[id(s)]:
                _finish_scene(proj, s)
        el = time.time() - t0
        part = f" [{f0}–{f1}]" if id(s) in left else ""
        log(f"  {s['id']}{part}: {n} кадров за {dt:.0f} c ({n / dt:.1f} fps) | всего {done}/{frames}, "
            f"осталось ~{el / done * (frames - done):.0f} c")
        sys.stdout.flush()

    if not workers:
        for s, out, f0, f1, key in jobs:
            _, n, dt = _render_scene_job(str(proj.root), s, ctx, sub_px, out, *args, f0, f1, key)
            finished(s, f0, f1, n, dt)
        return
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_render_scene_job, str(proj.root), s, ctx, sub_px, out, *args, f0, f1, key): (s, f0, f1)
                for s, out, f0, f1, key in jobs}
        for fu in as_completed(futs):
            _, n, dt = fu.result()
            finished(*futs[fu], n, dt)


def pick_scenes(tl, spec):
    """`--scenes ch01/s02,ch02/s05` → множество (глава, сцена); неизвестная сцена — стоп с подсказкой."""
    have = {(s["chapter"], s["id"]) for s in tl["scenes"]}
    out = set()
    for x in filter(None, (p.strip() for p in (spec or "").split(","))):
        ch, _, sid = x.partition("/")
        if (ch, sid) not in have:
            raise SystemExit(f"--scenes: нет сцены {x} (формат chNN/sNN)")
        out.add((ch, sid))
    return out


def render(proj: Project, chapter=None, workers=None, log=print, force=False, draft=False, scenes=None):
    """scenes — «ch01/s02,ch02/s05»: только эти сцены (правки по ревью, ROADMAP D1); прочие устаревшие — в отчёт."""
    tl, ctx = prepare(proj, draft)
    pick = pick_scenes(tl, scenes) if scenes else None
    todo = [s for s in tl["scenes"] if (chapter in (None, s["chapter"])) and (force or not is_fresh(proj, s))
            and (pick is None or (s["chapter"], s["id"]) in pick)]
    if pick is not None:
        rest = [f"{s['chapter']}/{s['id']}" for s in tl["scenes"]
                if (s["chapter"], s["id"]) not in pick and not is_fresh(proj, s)]
        if rest:
            log(f"Устарели и вне --scenes ({len(rest)}): {', '.join(rest[:12])}{' …' if len(rest) > 12 else ''}")
    if not todo:
        log("Все сцены актуальны — рендерить нечего.")
        return tl
    workers = workers or proj.cfg["render"].get("workers") or default_workers()
    log(f"{'Черновой рендер' if draft else 'Рендер'} {ctx['W']}×{ctx['H']}: {len(todo)} сцен, {sum(s['n_frames'] for s in todo)} кадров, процессов: {workers}")
    if pick is not None:
        log(f"Сцены: {', '.join(s['chapter'] + '/' + s['id'] for s in todo)}")
    render_scenes(proj, todo, ctx, workers, log, force)
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
