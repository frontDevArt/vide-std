"""Календарь студии (ROADMAP E4): `python -m studio --studio <id> calendar`.

Ролики студии по датам и стадиям `idea → brief → production → review → ready → published`. Стадию никто не пишет
руками — она выводится из файлов (как `status`):
- idea — пункт `plan.yaml` (D2) без брифа и проекта, или с `stage: idea` (batch такой проект не создаёт);
- brief — есть бриф (`brief:` пункта или `briefs/<slug>.md`), но сценарий не готов (фазы 1 и 3 `status`);
- production — сценарий готов, QA ✅ ещё не у всех выходов (очередь jobs — в пояснении). Готов — отчёт QA PASS
  новее финала и озвучка по текущему сценарию (`qa_pass`): устаревший после правки кода кэш сцен ролик не «расготавливает»;
- review — есть открытые комментарии ревью (D1), или ревью не утверждено, или студия `kind: client`, а ревью нет;
- ready — QA ✅, ревью закрыто, не опубликован на всех выходах (`published.yaml`, E1);
- published — запись `published.yaml` у каждого выхода.
Источники: пункты плана, проекты студии вне плана (кроме демо стиля `-demo`), брифы `briefs/*.md` без проекта.
Дата — день выхода из плана, у опубликованного — фактический. Просрочено — дата прошла, а не опубликован.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import batch, jobs, publish, review, workspace

STAGES = ("idea", "brief", "production", "review", "ready", "published")
MARK = {"idea": "💡", "brief": "📝", "production": "🎬", "review": "👀", "ready": "📦", "published": "✅"}
NAME = {"idea": "идея", "brief": "бриф", "production": "производство", "review": "ревью", "ready": "готов",
        "published": "опубликован"}
SOON = 3  # дней до выхода: идея или бриф без сценария — ⚠️
FILE = "CALENDAR.md"


def _date(v) -> dt.date | None:
    if v is None or isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def brief_topic(f: Path) -> str:
    """Тема брифа: первая строка `**…**` (шаблон briefs/_TEMPLATE.md), иначе имя файла."""
    for line in f.read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"\*\*(.+)\*\*", line.strip())
        if m:
            return m.group(1).strip()
    return f.stem


def entries(ws: workspace.Workspace) -> list[dict]:
    """Ролики студии: пункты плана, затем проекты вне плана, затем брифы без проекта."""
    out = []
    plan = batch.plan_path(ws)
    if plan.exists():
        for it in batch.load(plan)["items"]:
            out.append({**it, "from": "plan"})
    slugs = {e["slug"] for e in out}
    for root in workspace.projects(ws):
        if root.name in slugs or root.name.endswith("-demo"):
            continue
        from .project import load
        cfg = load(root).cfg
        pf = list(cfg.get("deliverables") or []) or [p for p in [cfg.get("platform")] if p]
        out.append({"slug": root.name, "topic": str(cfg.get("title") or root.name), "date": None, "brief": None,
                    "platforms": pf, "from": "project"})
        slugs.add(root.name)
    linked = {str(Path(e["brief"]).as_posix()) for e in out if e.get("brief")}
    if ws.briefs.exists():
        for f in sorted(ws.briefs.glob("*.md")):
            rel = f.relative_to(ws.root).as_posix()
            if f.name.startswith("_") or f.stem in slugs or rel in linked:
                continue
            out.append({"slug": f.stem, "topic": brief_topic(f), "date": None, "brief": rel, "platforms": [],
                        "from": "brief"})
    return out


def _brief(ws, e) -> Path | None:
    f = ws.root / e["brief"] if e.get("brief") else ws.briefs / f"{e['slug']}.md"
    return f if f.exists() else None


def qa_pass(t) -> bool:
    """QA ✅ готового финала выхода: отчёт PASS не старше финала, сценарий с тех пор не менялся (озвучка актуальна).
    Строже `status` не надо: после правки кода рисования кэш сцен устаревает (REFACTOR, правило 6), но готовый
    ролик от этого не перестаёт быть готовым."""
    fin, rep = t.final_path(), t.qa_dir / "report.md"
    if not (fin.exists() and rep.exists()) or rep.stat().st_mtime < fin.stat().st_mtime:
        return False
    if "Итог: **PASS**" not in rep.read_text(encoding="utf-8"):
        return False
    tl = t.build / "timeline.json"
    from .timing import source_hash
    return tl.exists() and json.loads(tl.read_text(encoding="utf-8")).get("src") == source_hash(t)


def stage(ws: workspace.Workspace, e: dict, queue=None) -> tuple[str, str, dt.date | None]:
    """(стадия, пояснение, дата публикации или None) ролика календаря."""
    root = ws.project(e["slug"])
    if not (root / "project.yaml").exists():
        f = _brief(ws, e)
        if e.get("stage") == "idea" or not f:
            return "idea", ("нужен бриф: /topic-to-brief" if ws.is_channel() else "нужен бриф"), None
        return "brief", f"бриф {f.relative_to(ws.root).as_posix()}, проекта нет (/new-video)", None
    from .project import load
    from .status import all_phases
    proj = load(root)
    outs = proj.outputs or [None]
    recs = publish.load(proj)
    done = [o for o in outs if any(r.get("out") == o for r in recs)]
    if len(done) == len(outs):
        first = min(recs, key=lambda r: str(r.get("date")))
        where = ", ".join(sorted({str(r.get("platform")) for r in recs}))
        return "published", f"{where}: {first['url']}", _date(first.get("date"))
    part = f"; опубликовано {len(done)}/{len(outs)} ({', '.join(done)})" if done else ""
    targets = proj.targets()
    finished = all(qa_pass(t) for t in targets)  # готовый ролик: фазы (и пересчёт кэша сцен) не нужны
    ph = [] if finished else all_phases(proj)
    script = "3" if proj.cfg.get("cutdown") else "13"  # у нарезки (B4) бриф и сценарий — у исходника
    need = next((n for n, ok, _ in ph if not ok and n[:1] in script), None)
    if need:
        return "brief", f"нужно: {need}" + (f" (/new-video {e['brief']})" if e.get("brief") else " (/new-video)"), None
    revs = [review.load(t) for t in targets if review.path(t).exists()]
    opened = sum(len(review.open_comments(d)) for d in revs)
    if opened:
        return "review", f"открытых комментариев {opened} (/review-fix {e['slug']})" + part, None
    if not finished:
        failed = [t.out or "" for t in targets if (t.qa_dir / "report.md").exists()
                  and "Итог: **FAIL**" in (t.qa_dir / "report.md").read_text(encoding="utf-8")]
        q = [j for j in (queue if queue is not None else jobs.load()) if batch._job_root(j) == root.resolve()]
        last = q[-1] if q else None
        if last and last["status"] in jobs.ACTIVE:
            return "production", f"{'в очереди' if last['status'] == 'queued' else 'рендер'}: задача {last['id']}", None
        if last and last["status"] == "failed":
            return "production", f"задача {last['id']} упала — лог {jobs.log_path(last)}", None
        if failed:
            return "production", "QA ❌" + (f" ({', '.join(failed)})" if any(failed) else "") + f": python -m studio qa {e['slug']}" + part, None
        nxt = next((n for n, ok, _ in ph if not ok), "")
        return "production", f"дальше: {nxt}" + part, None
    if any(d.get("status") != "approved" for d in revs):
        return "review", f"ревью не утверждено (python -m studio review {e['slug']})" + part, None
    if not revs and ws.config.get("kind") == "client":
        return "review", f"клиент не утвердил: python -m studio review {e['slug']}" + part, None
    return "ready", f"QA ✅ → python -m studio publish {e['slug']}" + part, None


def rows(ws: workspace.Workspace, today: dt.date | None = None) -> list[dict]:
    """Строки календаря с стадией и пометкой о сроке; по дате, без даты — в конце по стадии."""
    today = today or dt.date.today()
    queue = jobs.load()
    res = []
    for e in entries(ws):
        st, det, pub = stage(ws, e, queue)
        plan = _date(e.get("date"))
        r = {**e, "stage": st, "detail": det, "plan_date": plan, "date": pub or plan, "warn": None}
        if st == "published":
            if plan and pub and pub != plan:
                r["warn"] = f"по плану {plan.isoformat()}"
        elif plan and plan < today:
            r["warn"] = f"⚠️ просрочен на {(today - plan).days} дн."
        elif plan and st in ("idea", "brief") and (plan - today).days <= SOON:
            r["warn"] = f"⚠️ выход через {(plan - today).days} дн., сценария нет"
        res.append(r)
    res.sort(key=lambda r: (r["date"] is None, r["date"] or dt.date.min, STAGES.index(r["stage"]), r["slug"]))
    return res


def select(rs: list[dict], since=None, until=None, stages=None) -> list[dict]:
    """Фильтр: даты [since, until] (ролики без даты остаются, если нет границ), стадии."""
    out = []
    for r in rs:
        d = r["date"]
        if (since or until) and d is None:
            continue
        if since and d < since or until and d > until:
            continue
        if stages and r["stage"] not in stages:
            continue
        out.append(r)
    return out


def funnel(rs: list[dict]) -> str:
    n = {s: sum(1 for r in rs if r["stage"] == s) for s in STAGES}
    return " → ".join(f"{MARK[s]} {NAME[s]} {n[s]}" for s in STAGES)


WEEKDAY = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _day(d: dt.date | None) -> str:
    return f"{d.isoformat()} {WEEKDAY[d.weekday()]}" if d else "без даты"


def table(ws: workspace.Workspace, rs: list[dict], log=print):
    log(f"Календарь {ws.name}: роликов {len(rs)}")
    month = object()
    for r in rs:
        m = r["date"].strftime("%Y-%m") if r["date"] else None
        if m != month:
            log(f"== {m or 'без даты'} ==")
            month = m
        pf = ",".join(r.get("platforms") or []) or "—"
        log(f"  {_day(r['date']):<13} {MARK[r['stage']]} {NAME[r['stage']]:<12} {r['slug']:<28} {pf:<22} "
            f"{r['detail']}" + (f"  {r['warn']}" if r["warn"] else ""))
    log("Воронка: " + funnel(rs))


def markdown(ws: workspace.Workspace, rs: list[dict], today: dt.date | None = None) -> Path:
    """studios/<id>/CALENDAR.md — тот же календарь таблицами по месяцам (снимок, пересоздаётся командой)."""
    today = today or dt.date.today()
    lines = [f"# Календарь — {ws.name}", "",
             f"Снимок {today.isoformat()}: `python -m studio --studio {ws.id} calendar --md`. Стадии выводятся из файлов "
             "(plan.yaml, брифы, проекты, ревью, published.yaml) — правьте их, не этот файл.", "",
             "Воронка: " + funnel(rs), ""]
    month = object()
    for r in rs:
        m = r["date"].strftime("%Y-%m") if r["date"] else None
        if m != month:
            lines += ["", f"## {m or 'Без даты'}", "", "| Дата | Стадия | Ролик | Площадки | Что дальше |",
                      "|---|---|---|---|---|"]
            month = m
        det = (r["detail"] + (f" — {r['warn']}" if r["warn"] else "")).replace("|", "\\|")
        topic = str(r.get("topic") or "").replace("|", "\\|")
        lines.append(f"| {_day(r['date'])} | {MARK[r['stage']]} {NAME[r['stage']]} | **{r['slug']}** — {topic} | "
                     f"{', '.join(r.get('platforms') or []) or '—'} | {det} |")
    f = ws.root / FILE
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f
