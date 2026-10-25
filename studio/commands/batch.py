"""batch — серия по контент-плану студии (ROADMAP D2, studio/batch.py): проекты → очередь рендеров (studio/jobs.py)."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from .. import workspace


def add(sp):
    q = sp.add_parser("batch", help="серия по plan.yaml студии: создать проекты, рендеры — в очередь")
    q.add_argument("--plan", metavar="ФАЙЛ", help="контент-план (без флага — plan.yaml текущей студии, --studio <id>)")
    q.add_argument("--list", action="store_true", help="только таблица серии, ничего не создавать и не ставить")
    q.add_argument("--run", action="store_true", help="сразу выполнить очередь (ночной запуск — scripts/night-batch.ps1)")
    q.add_argument("--yes", action="store_true", help="согласие на платный синтез (elevenlabs) для задач серии")
    q.add_argument("--until", metavar="ГГГГ-ММ-ДД", help="только ролики с датой выхода не позже этой")
    q.add_argument("--only", metavar="slug1,slug2", help="только эти ролики плана")
    q.add_argument("--workers", type=int, help="процессов рендера на задачу")


def _workspace(plan):
    """Студия контент-плана: --plan studios/<id>/plan.yaml → эта студия; без флага — текущая."""
    return workspace.at_dir(Path(plan).parent) if plan else workspace.current()


def run(a):
    from .. import batch, jobs
    ws = _workspace(a.plan)
    plan = batch.load(a.plan or batch.plan_path(ws))
    try:
        until = dt.date.fromisoformat(a.until) if a.until else None
    except ValueError:
        raise SystemExit(f"--until {a.until}: нужно ГГГГ-ММ-ДД")
    only = {s.strip() for s in a.only.split(",") if s.strip()} if a.only else None
    items = batch.select(plan["items"], until, only)
    if only and len(items) < len(only):
        raise SystemExit(f"--only: нет в плане {', '.join(sorted(only - {i['slug'] for i in items}))}")
    if a.list:
        batch.report(ws, plan, items)
        return 0
    queue = jobs.load()
    for it in items:
        code, _ = batch.state(ws, it, queue)
        if code == "new":
            batch.create(ws, it)
        elif code in ("ready", "failed"):
            j, fresh = jobs.add(batch.job_argv(ws, it, a.yes, a.workers), title=f"all {it['slug']}")
            print(f"{'⏳ в очередь' if fresh else '⏳ уже в очереди'}: {it['slug']} ({j['id']})")
    if a.run:
        res = jobs.run()
        if res is None:
            print("Задачи серии выполнит работающий исполнитель; итог — python -m studio batch --list")
    cnt = batch.report(ws, plan, items)
    if not a.run and cnt.get("queued"):
        print("Выполнить очередь: python -m studio jobs run (или batch --run)")
    return 1 if cnt.get("failed") else 0
