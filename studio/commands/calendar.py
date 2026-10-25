"""calendar — календарь студии: ролики по датам и стадиям idea → … → published (ROADMAP E4, studio/calendar.py)."""
from __future__ import annotations

import datetime as dt

from .. import workspace


def add(sp):
    q = sp.add_parser("calendar", help="календарь студии: plan.yaml + стадии роликов (idea → brief → production → "
                                       "review → ready → published)")
    q.add_argument("--from", dest="since", metavar="ГГГГ-ММ-ДД", help="только ролики с датой не раньше этой")
    q.add_argument("--until", metavar="ГГГГ-ММ-ДД", help="только ролики с датой не позже этой")
    q.add_argument("--month", metavar="ГГГГ-ММ", help="только этот месяц")
    q.add_argument("--stage", metavar="s1,s2", help="только эти стадии: idea, brief, production, review, ready, published")
    q.add_argument("--md", action="store_true", help="записать снимок в CALENDAR.md студии")


def _day(v, flag):
    try:
        return dt.date.fromisoformat(v) if v else None
    except ValueError:
        raise SystemExit(f"{flag} {v}: нужно ГГГГ-ММ-ДД")


def run(a):
    from .. import calendar as C
    ws = workspace.current()
    since, until = _day(a.since, "--from"), _day(a.until, "--until")
    if a.month:
        try:
            m = dt.date.fromisoformat(a.month + "-01")
        except ValueError:
            raise SystemExit(f"--month {a.month}: нужно ГГГГ-ММ")
        nxt = (m.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        since, until = max(since or m, m), min(until or nxt, nxt - dt.timedelta(days=1))
    stages = {s.strip() for s in a.stage.split(",") if s.strip()} if a.stage else None
    if stages and stages - set(C.STAGES):
        raise SystemExit(f"--stage: нет стадии {', '.join(sorted(stages - set(C.STAGES)))} (есть: {', '.join(C.STAGES)})")
    rs = C.select(C.rows(ws), since, until, stages)
    if not rs:
        print(f"Календарь {ws.name}: пусто (план — {C.batch.plan_path(ws)}, образец — studio/batch.py)")
        return 0
    C.table(ws, rs)
    if a.md:
        print(f"📅 {C.markdown(ws, rs)}")
    return 0
