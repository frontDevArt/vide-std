"""Проверка вёрстки «контент в безопасной зоне»: шаблон сцены рисуется на прозрачный слой отдельно от фона
и субтитров, рамка непрозрачных пикселей сравнивается с полями кадра (`qa.safe_margin`, доля стороны, по умолчанию 4 %).

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


def scan(proj: Project, chapter=None, margin=None) -> list[dict]:
    """Сцены, где контент заходит в поля: {chapter, id, template, margins: {side: доля}, bad: [сторона по-русски]}."""
    from .render import make_template, prepare
    if margin is None:
        margin = float(proj.cfg.get("qa", {}).get("safe_margin", 0.04))
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
        bad = [ru for side, ru in SIDES if m[side] < margin - 1e-9]
        if bad:
            out.append({"chapter": s["chapter"], "id": s["id"], "template": s["template"], "margins": m, "bad": bad})
    return out


def message(issue, margin) -> str:
    sides = ", ".join(f"{ru} {issue['margins'][side] * 100:.0f} %" for side, ru in SIDES if ru in issue["bad"])
    return f"{issue['chapter']}/{issue['id']} {issue['template']}: контент у края — {sides} (поле {margin * 100:g} %)"


def report(proj: Project, chapter=None, log=print) -> list[dict]:
    margin = float(proj.cfg.get("qa", {}).get("safe_margin", 0.04))
    issues = scan(proj, chapter, margin)
    for i in issues:
        log("  ⚠️  " + message(i, margin))
    return issues


def qa_check(proj: Project, add):
    """Строка отчёта qa: add(статус, имя, подробности). WARN на итог не влияет."""
    margin = float(proj.cfg.get("qa", {}).get("safe_margin", 0.04))
    issues = scan(proj, margin=margin)
    det = "; ".join(message(i, margin) for i in issues[:4]) + (f"; ещё {len(issues) - 4}" if len(issues) > 4 else "")
    add("WARN" if issues else "PASS", "Контент в безопасной зоне", det or f"поле {margin * 100:g} %")
