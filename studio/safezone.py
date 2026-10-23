"""Проверка вёрстки «контент в безопасной зоне»: шаблон сцены рисуется на прозрачный слой отдельно от фона
и субтитров, рамка непрозрачных пикселей сравнивается с полями кадра (`qa.safe_margin`, доля стороны, по умолчанию 4 %);
у проекта с `platform:` — с безопасной зоной площадки и её интерфейсом (studio/platforms.py, ROADMAP B1).

Кадры — те же, что у `stills`: начало сцены, середины битов, конец. Пока только ⚠️: вертикаль `lab_*` не свёрстана
(channel/STYLE.md §12), после ROADMAP B2 станет ❌. Модуль не в `render.code_hash` — правка проверки не сбрасывает кэш рендера.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .project import Project

ALPHA = 40  # пиксели слабее — мягкие тени и свечения, не контент
SIDES = (("left", "слева"), ("top", "сверху"), ("right", "справа"), ("bottom", "снизу"))


def _times(s):
    return [0.12] + [(b["t0"] + b["t1"]) / 2 for b in s["beats"]] + [s["dur"] - 0.1]


def content_box(ctx, tpl, scene, t):
    """Рамка (x0, y0, x1, y1) непрозрачных пикселей слоя контента в момент t сцены или None (пустой кадр).
    Без дрейфа камеры (`lab.apply_camera`, масштаб до 103 %): он общий для всего кадра и не вёрстка — с ним
    свёрстанная горизонталь `lab` (поля ~5 %) мигала бы ⚠️ на 3,5 %."""
    layer = Image.new("RGBA", (ctx["W"], ctx["H"]), (0, 0, 0, 0))
    tpl.draw(layer, t, scene["start_frame"] / ctx["fps"] + t)
    ys, xs = np.nonzero(np.asarray(layer)[:, :, 3] > ALPHA)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1) if len(xs) else None


def zone(proj: Project) -> tuple[dict, tuple]:
    """Поля по сторонам ({side: доля}) и прямоугольники интерфейса: `qa.safe_margin`, а у проекта с `platform:` —
    не меньше полей площадки плюс её интерфейс (колонка кнопок справа у TikTok/Shorts; studio/platforms.py, ROADMAP B1)."""
    from .platforms import of
    base = float(proj.cfg.get("qa", {}).get("safe_margin", 0.04))
    p = of(proj)
    if not p:
        return {side: base for side, _ in SIDES}, ()
    return {side: max(base, getattr(p.safe, side)) for side, _ in SIDES}, p.ui


def _hits(box, ui, W, H) -> bool:
    x0, y0, x1, y1 = ui.box
    return box[2] > x0 * W and box[0] < x1 * W and box[3] > y0 * H and box[1] < y1 * H


def scan(proj: Project, chapter=None, margin=None) -> list[dict]:
    """Сцены, где контент заходит в поля или под интерфейс площадки:
    {chapter, id, template, margins: {side: доля}, bad: [сторона по-русски], ui: [что перекрыто], need: {side: поле}}.
    `margin` — одно поле на все стороны без интерфейса площадки (как до B1)."""
    from .render import make_template, prepare
    if margin is None:
        need, uis = zone(proj)
    else:
        need, uis = {side: float(margin) for side, _ in SIDES}, ()
    tl, ctx = prepare(proj)
    W, H = ctx["W"], ctx["H"]
    out = []
    for s in tl["scenes"]:
        if chapter not in (None, s["chapter"]):
            continue
        tpl = make_template(ctx, s)
        boxes = [content_box(ctx, tpl, s, max(0.0, min(s["dur"] - 1 / ctx["fps"], t))) for t in _times(s)]
        boxes = [b for b in boxes if b]
        if not boxes:
            continue
        m = {"left": min(b[0] for b in boxes) / W, "top": min(b[1] for b in boxes) / H,
             "right": 1 - max(b[2] for b in boxes) / W, "bottom": 1 - max(b[3] for b in boxes) / H}
        bad = [ru for side, ru in SIDES if m[side] < need[side] - 1e-9]
        ui = [u.name for u in uis if any(_hits(b, u, W, H) for b in boxes)]
        if bad or ui:
            out.append({"chapter": s["chapter"], "id": s["id"], "template": s["template"], "margins": m, "bad": bad,
                        "ui": ui, "need": need})
    return out


def message(issue, margin=None) -> str:
    """`margin` — одно поле для подписи (как до B1); без него — поле каждой стороны из issue["need"]."""
    need = issue.get("need") or {}
    uniform = margin is not None or len(set(need.values())) <= 1
    m = margin if margin is not None else next(iter(need.values()), 0.04)
    parts = []
    if issue["bad"]:
        sides = ", ".join(f"{ru} {issue['margins'][side] * 100:.0f} %"
                          + ("" if uniform else f" из {need[side] * 100:g} %")
                          for side, ru in SIDES if ru in issue["bad"])
        parts.append(f"контент у края — {sides}" + (f" (поле {m * 100:g} %)" if uniform else ""))
    if issue.get("ui"):
        parts.append("под интерфейсом площадки — " + ", ".join(issue["ui"]))
    return f"{issue['chapter']}/{issue['id']} {issue['template']}: " + "; ".join(parts)


def _label(proj) -> str:
    from .platforms import of
    need, _ = zone(proj)
    p = of(proj)
    if p:
        z = "/".join(f"{need[side] * 100:g}" for side in ("top", "bottom", "left", "right"))
        return f"зона {p.id}: поля в/н/л/п {z} %" + (" + интерфейс" if p.ui else "")
    return f"поле {need['top'] * 100:g} %"


def report(proj: Project, chapter=None, log=print) -> list[dict]:
    issues = scan(proj, chapter)
    for i in issues:
        log("  ⚠️  " + message(i))
    return issues


def qa_check(proj: Project, add):
    """Строка отчёта qa: add(статус, имя, подробности). WARN на итог не влияет."""
    issues = scan(proj)
    det = "; ".join(message(i) for i in issues[:4]) + (f"; ещё {len(issues) - 4}" if len(issues) > 4 else "")
    add("WARN" if issues else "PASS", "Контент в безопасной зоне", det or _label(proj))
