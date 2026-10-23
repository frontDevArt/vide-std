"""studios — студии (workspace) и их проекты (ROADMAP A1): `default` в корне и `studios/<id>/`."""
from __future__ import annotations

from .. import workspace

LOG = False  # только чтение


def add(sp):
    sp.add_parser("studios", help="студии и их проекты")


def check(ws: workspace.Workspace) -> list[str]:
    """Замечания к studio.yaml: тип студии и `defaults` по схеме project.yaml."""
    from ..config import check as check_cfg
    cfg = ws.config
    out = []
    if ws.id != workspace.DEFAULT and cfg.get("kind") not in workspace.KINDS:
        out.append(f"kind: {cfg.get('kind')!r} — нужно одно из {', '.join(workspace.KINDS)}")
    out += [f"defaults: {w}" for w in check_cfg(cfg.get("defaults") or {})]
    return out


def run(a):
    cur = workspace.current()
    for ws in workspace.studios():
        cfg = ws.config
        mark = "*" if ws.root.resolve() == cur.root.resolve() else " "
        where = ws.root.relative_to(workspace.ROOT).as_posix() if ws.id != workspace.DEFAULT else "."
        kind = cfg.get("kind") or "—"
        langs = ", ".join(cfg.get("languages") or []) or "—"
        projs = workspace.projects(ws)
        print(f"{mark} {ws.id:<22} {kind:<8} {langs:<8} {where}  — {ws.name}")
        for w in check(ws):
            print(f"    ⚠️  studio.yaml: {w}")
        if projs:
            print("    проекты: " + ", ".join(p.name for p in projs))
        else:
            print("    проектов нет")
    print("\nСтудия для команды: python -m studio --studio <id> <команда>; без флага проект ищется во всех студиях.")
    return 0
