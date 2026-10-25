"""jobs — очередь задач студии на этой машине (ROADMAP D2, studio/jobs.py): список, выполнение, повтор, чистка."""
from __future__ import annotations


def add(sp):
    q = sp.add_parser("jobs", help="очередь задач: list | run | retry <id|failed> | clear")
    q.add_argument("action", nargs="?", default="list", choices=("list", "run", "retry", "clear"))
    q.add_argument("id", nargs="?", help="retry: id задачи или failed — все упавшие")
    q.add_argument("--all", action="store_true", help="clear: и упавшие (по умолчанию — только сделанные)")


def run(a):
    from .. import jobs
    if a.action == "list":
        print(jobs.table(jobs.load()))
        pid = jobs.runner_pid()
        print(f"Исполнитель: {'работает, PID ' + str(pid) if pid else 'не запущен'} — папка {jobs.DIR}")
        return 0
    if a.action == "run":
        res = jobs.run()
        if res is None:
            return 0
        print(f"Очередь пройдена: ✅ {res['done']}, ❌ {res['failed']}")
        return 1 if res["failed"] else 0
    if a.action == "retry":
        if not a.id:
            raise SystemExit("retry: укажите id задачи (python -m studio jobs) или failed")
        ids = [j["id"] for j in jobs.load() if j["status"] == "failed"] if a.id == "failed" else [a.id]
        for jid in ids:
            try:
                j = jobs.retry(jid)
            except KeyError:
                raise SystemExit(f"Нет задачи {jid} — python -m studio jobs")
            print(f"⏳ {j['id']} {j['title']} — снова в очереди")
        return 0
    n = jobs.clear(statuses=("done", "failed") if a.all else ("done",))
    print(f"Убрано задач: {n}")
    return 0
