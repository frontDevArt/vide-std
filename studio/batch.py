"""Серии роликов (ROADMAP D2): контент-план студии `studios/<id>/plan.yaml` → проекты → очередь рендеров.

    series: autumn-drop                     # имя серии (для отчёта)
    defaults: {kind: short-hook, platforms: [tiktok], duration: 20}
    items:
      - date: 2026-11-03                    # день выхода
        topic: "Three ways to brew"         # тема → `new`
        slug: brew-three                    # без него — из темы
        brief: briefs/brew-three.md         # бриф для /new-video (необязательно)
        platforms: [tiktok, instagram-reels] # первая — platform проекта, две и больше — deliverables
        kind: promo                         # и format, duration, lang, tts — как флаги `new`
      - topic: "Holiday gift guide"         # без даты — бэклог
        stage: idea                         # идея (ROADMAP E4): batch проект не создаёт, calendar показывает 💡

`python -m studio batch`: создаёт проекты, которых ещё нет; проекты с готовым сценарием (бриф и script/ по фазам
`status`) и без QA ✅ ставит в очередь (`all <проект>`, studio/jobs.py); `--run` — сразу выполняет очередь.
Сценарии пишет Claude (`/new-video`, днём) — ночью очередь рендерит без присмотра, утром `batch --list` — итог.
"""
from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import yaml

from . import jobs, workspace

ITEM_KEYS = {"date", "topic", "slug", "brief", "platforms", "kind", "format", "duration", "lang", "tts", "stage"}
STAGES = ("idea",)  # `stage:` пункта — только задержать идею; остальные стадии calendar выводит из файлов (E4)


def plan_path(ws) -> Path:
    return ws.root / "plan.yaml"


def load(path) -> dict:
    """plan.yaml → {series, items: [пункт с умолчаниями]}; ошибки — SystemExit со всеми проблемами сразу."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Нет контент-плана: {path} (образец — docs/ROADMAP.md, D2; studio/batch.py)")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = raw.get("defaults") or {}
    from . import kinds
    from .commands.new import slugify
    from .platforms import get as platform
    errs, items, seen = [], [], set()
    for i, it in enumerate(raw.get("items") or [], 1):
        it = {**base, **(it or {})}
        where = f"items[{i}]"
        bad = set(it) - ITEM_KEYS
        if bad:
            errs.append(f"{where}: неизвестные поля {', '.join(sorted(bad))} (есть: {', '.join(sorted(ITEM_KEYS))})")
        if not str(it.get("topic") or "").strip():
            errs.append(f"{where}: нет topic")
            continue
        it["slug"] = str(it.get("slug") or slugify(it["topic"]))
        if it["slug"] in seen:
            errs.append(f"{where}: slug {it['slug']} повторяется")
        seen.add(it["slug"])
        pf = it.get("platforms") or []
        it["platforms"] = [pf] if isinstance(pf, str) else list(pf)
        for p in it["platforms"]:
            try:
                platform(p)
            except KeyError as e:
                errs.append(f"{where}: {e.args[0]}")
        if it.get("stage") is not None and it["stage"] not in STAGES:
            errs.append(f"{where}: stage {it['stage']!r} — можно только idea (остальное calendar видит по файлам)")
        if it.get("kind") and it["kind"] not in kinds.KINDS:
            errs.append(f"{where}: нет типа {it['kind']} (python -m studio kinds)")
        d = it.get("date")
        if d is not None and not isinstance(d, dt.date):
            try:
                d = dt.date.fromisoformat(str(d))
            except ValueError:
                errs.append(f"{where}: дата {d!r} — нужно ГГГГ-ММ-ДД")
        it["date"] = d
        items.append(it)
    if errs:
        raise SystemExit(f"❌ {path}:\n  " + "\n  ".join(errs))
    return {"series": raw.get("series") or path.parent.name, "items": items}


def create(ws, it, log=print) -> Path:
    """Проект пункта плана через `new` (те же умолчания студии); площадок больше одной — deliverables."""
    from .commands import new
    pf = it["platforms"]
    a = argparse.Namespace(topic=str(it["topic"]), slug=it["slug"], format=it.get("format"),
                           platform=pf[0] if pf else None, duration=it.get("duration"), lang=it.get("lang"),
                           kind=it.get("kind"), tts=it.get("tts"))
    with workspace.use(ws):
        new._create(a, ws)
    root = ws.project(it["slug"])
    f = root / "project.yaml"
    y = f.read_text(encoding="utf-8")
    head = f"# Серия (ROADMAP D2, plan.yaml): выход {it['date'] or 'без даты'}" + (
        f"; бриф — {it['brief']}" if it.get("brief") else "") + "\n"
    if len(pf) > 1:
        y += f"deliverables: [{', '.join(pf)}]   # площадки из plan.yaml (ROADMAP B3)\n"
    f.write_text(head + y, encoding="utf-8")
    return root


def state(ws, it, queue=None) -> tuple[str, str]:
    """(код, пояснение): new — проекта нет; draft — нужен бриф/сценарий (дело Claude); queued/running — в очереди;
    ready — можно рендерить; failed — задача упала; done — QA ✅ у всех выходов."""
    root = ws.project(it["slug"])
    if not (root / "project.yaml").exists():
        if it.get("stage") == "idea":
            return "idea", "идея (stage: idea) — проект не создаём"
        return "new", "проекта нет"
    q = [j for j in (queue if queue is not None else jobs.load()) if _job_root(j) == root.resolve()]
    last = q[-1] if q else None
    if last and last["status"] in jobs.ACTIVE:
        return last["status"], f"задача {last['id']}"
    from .project import load as load_project
    from .status import all_phases
    ph = all_phases(load_project(root))
    qa = [ok for n, ok, _ in ph if n.startswith("8 ")]
    if qa and all(qa):
        return "done", "QA ✅"
    need = next((n for n, ok, _ in ph if not ok and n[:1] in "13"), None)
    if need:
        return "draft", f"нужно: {need}" + (f" (/new-video {it['brief']})" if it.get("brief") else " (/new-video)")
    if last and last["status"] == "failed":
        return "failed", f"задача {last['id']} упала, код {last['rc']} — лог {jobs.log_path(last)}"
    first = next((n for n, ok, _ in ph if not ok and n[:1] in "45678"), "")
    return "ready", f"сценарий готов, дальше: {first}"


def _job_root(j):
    a = j.get("argv") or []
    return Path(a[1]).resolve() if len(a) > 1 and a[0] == "all" else None


def job_argv(ws, it, yes=False, workers=None) -> list[str]:
    argv = ["all", str(ws.project(it["slug"]).resolve())]
    if yes:
        argv.append("--yes")
    if workers:
        argv += ["--workers", str(workers)]
    return argv


def select(items, until=None, only=None):
    """Пункты плана: дата ≤ until (пункты без даты — всегда), only — список slug."""
    out = []
    for it in items:
        if until and it["date"] and it["date"] > until:
            continue
        if only and it["slug"] not in only:
            continue
        out.append(it)
    return out


MARK = {"idea": "💡", "new": "🆕", "draft": "✍️ ", "ready": "⬜", "queued": "⏳", "running": "▶", "failed": "❌", "done": "✅"}


def report(ws, plan, items, log=print) -> dict:
    """Таблица серии; → {код: число}."""
    queue = jobs.load()
    cnt: dict = {}
    log(f"Серия {plan['series']} ({ws.name}), роликов: {len(items)}")
    for it in items:
        code, det = state(ws, it, queue)
        cnt[code] = cnt.get(code, 0) + 1
        pf = ",".join(it["platforms"]) or "—"
        log(f"  {MARK[code]} {str(it['date'] or '—'):<10}  {it['slug']:<28} {pf:<24} {det}")
    log("Итог: " + ", ".join(f"{MARK[k].strip()} {k} {v}" for k, v in cnt.items()))
    return cnt
