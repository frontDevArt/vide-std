"""review — ревью с комментариями по таймкодам (ROADMAP D1, studio/review.py)."""
from __future__ import annotations

from . import project_parser
from ..project import load, resolve_project


def add(sp):
    q = project_parser(sp, "review", "ревью: страница с комментариями по таймкодам (127.0.0.1)")
    q.add_argument("--port", type=int, default=8765, help="порт на 127.0.0.1 (8765; 0 — свободный)")
    q.add_argument("--no-open", action="store_true", help="не открывать браузер")
    q.add_argument("--list", action="store_true", help="открытые комментарии текстом для Claude (без сервера)")
    q.add_argument("--done", metavar="c1,c2", help="закрыть комментарии после правок")
    q.add_argument("--status", choices=("draft", "approved"), help="статус версии")
    q.add_argument("--out", metavar="ВЫХОД", help="выход из deliverables (у каждого свои комментарии)")


def run(a):
    from .. import review as R
    proj = load(resolve_project(a.project))
    if a.out:
        proj = proj.targets(a.out)[0]
    if a.done or a.status or a.list:
        try:
            for cid in filter(None, (a.done or "").split(",")):
                R.update(proj, cid.strip(), status="done")
                print(f"✅ {cid.strip()} закрыт")
            if a.status:
                R.set_status(proj, a.status)
                print(f"Версия: {a.status}")
        except KeyError as e:
            raise SystemExit(f"Нет комментария {e.args[0]} — python -m studio review {proj.slug} --list")
        except ValueError as e:
            raise SystemExit(f"❌ {e}")
        if a.list:
            print(R.prompt(proj))
        return 0
    srv = R.make_server(proj, a.port)
    u = R.url(srv)
    print(f"Ревью {proj.slug}: {u}  (видео: {srv.RequestHandlerClass.video})\n"
          f"Комментарии: {R.path(proj)}\nCtrl+C — остановить.", flush=True)
    if not a.no_open:
        import webbrowser
        webbrowser.open(u)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
