"""analytics — цифры опубликованных роликов студии → studios/<id>/analytics/ для радара и брифов (ROADMAP E3, studio/analytics.py)."""
from __future__ import annotations

from .. import workspace


def add(sp):
    q = sp.add_parser("analytics", help="цифры роликов студии (просмотры, удержание, CTR) → analytics/REPORT.md для радара")
    q.add_argument("--fetch", action="store_true", help="YouTube: Analytics API + отчёт показов (CTR), только чтение")
    q.add_argument("--auth", action="store_true", help="войти в канал студии заново (с правом читать аналитику)")
    q.add_argument("--import", dest="csv", metavar="CSV", help="выгрузка таблицы из YouTube Studio")
    q.add_argument("--set", nargs="+", metavar=("ССЫЛКА", "метрика=число"),
                   help="цифры руками (TikTok, Instagram): --set <ссылка> views=1200 ctr=4.1 avg_view_pct=55")
    q.add_argument("--list", action="store_true", help="только напечатать цифры, отчёт не писать")


def run(a):
    from .. import analytics as A, youtube
    ws = workspace.current()
    if a.auth:
        youtube.auth(ws)
        return 0
    rows = A.videos(ws)
    if a.list:
        A.table(rows)
        return 0
    if a.set and len(a.set) < 2:
        raise SystemExit("--set: <ссылка> и хотя бы одна метрика=число")
    if a.fetch:
        A.fetch(ws, rows)
    if a.csv:
        A.import_csv(rows, a.csv)
    if a.set:
        A.set_manual(rows, a.set[0], a.set[1:])
    A.save(ws, rows)
    f = A.report(ws, rows)
    n = sum(1 for r in rows if r["metrics"].get("views") is not None)
    print(f"📊 {ws.name}: роликов {len(rows)}, с цифрами {n} → {f}")
    return 0
