"""demo — демо стиля 10–15 с в projects/<slug>-demo/ (channel/STYLE.md §14)."""
from __future__ import annotations

import shutil

from .. import workspace
from ..project import load, resolve_project


def add(sp):
    q = sp.add_parser("demo", help="демо стиля 10–15 с в projects/<slug>-demo/ (STYLE §14)")
    q.add_argument("project")
    q.add_argument("--no-render", action="store_true", help="только создать проект демо")
    q.add_argument("--workers", type=int)
    q.add_argument("--yes", action="store_true", help="подтвердить платный синтез (elevenlabs)")


def run(a):
    """Стиль, формат, язык и голос — из проекта, сценарий — projects/<slug>/demo/ch01.yaml (иначе заготовка
    _template/demo), шаблоны проекта — копией."""
    import yaml
    from .all import run as run_all
    src = resolve_project(a.project)
    if src.name.endswith("-demo"):
        raise SystemExit("Это уже демо-проект — укажите исходный")
    script = src / "demo" / "ch01.yaml"
    if not script.exists():
        ws = workspace.current()
        script = ws.template / "demo" / "ch01.yaml"
        print(f"⚠️  нет {src.name}/demo/ch01.yaml — беру заготовку {script.relative_to(ws.root)} "
              "(без метафоры ролика; язык заготовки — en)")
    dst = src.parent / f"{src.name}-demo"
    (dst / "script").mkdir(parents=True, exist_ok=True)
    with open(src / "project.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg.update(title=f"style demo: {cfg.get('title', src.name)}", target_duration=None, chapters=["ch01"])
    # демо стиля — не ролик: финала с логотипом и призывом в нём нет (правила студии, ROADMAP D4)
    cfg["done_means"] = list(cfg.get("done_means") or []) + [{"logo_in_final": False}, {"cta_in_final": False}]
    with open(dst / "project.yaml", "w", encoding="utf-8") as f:
        f.write(f"# Сгенерировано `python -m studio demo {src.name}` — правьте исходный проект и demo/ch01.yaml.\n")
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    shutil.copyfile(script, dst / "script" / "ch01.yaml")
    if (src / "templates").exists():
        shutil.copytree(src / "templates", dst / "templates", dirs_exist_ok=True)
    print(f"Демо-проект: {dst}")
    if a.no_render:
        return 0
    a.project, a.fast, a.out = str(dst), False, None  # all ждёт --out (B3); у демо один выход
    rc = run_all(a)
    if not (dst / "build" / "timeline.json").exists():
        return rc or 1
    from ..timing import load_timeline
    dur = load_timeline(load(dst))["duration"]
    if not 10 <= dur <= 15.5:
        print(f"⚠️  демо {dur:.1f} c — нужно 10–15 c: поправьте текст demo/ch01.yaml")
    print(f"Демо: {load(dst).final_path()} ({dur:.1f} c) — показать пользователю и ждать утверждения")
    return rc
