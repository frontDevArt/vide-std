"""ROADMAP E4: календарь студии — plan.yaml + стадии idea → brief → production → review → ready → published
(studio/calendar.py, команда calendar). Рендера нет: «готовый» ролик — файлы финала, озвучки и отчёта QA (_finish)."""
import datetime as dt
import json
import shutil

import pytest
import yaml

from studio import batch, calendar as C, cli, jobs, project, review, workspace
from studio.selftest import KIND_DEMOS
from studio.timing import source_hash

TODAY = dt.date(2026, 11, 10)
PLAN = """
series: autumn
defaults: {kind: short-hook, platforms: [tiktok], duration: 15, lang: en, tts: fake}
items:
  - {topic: "Holiday gift guide", stage: idea}
  - {date: 2026-11-04, topic: "Late idea", slug: late}
  - {date: 2026-11-12, topic: "Briefed", slug: briefed, brief: briefs/briefed.md}
  - {date: 2026-11-14, topic: "Empty project", slug: empty}
  - {date: 2026-11-16, topic: "In production", slug: prod}
  - {date: 2026-11-18, topic: "Under review", slug: rev}
  - {date: 2026-11-20, topic: "Two outputs", slug: two, platforms: [tiktok, instagram-reels]}
  - {date: 2026-11-08, topic: "Out already", slug: out}
"""
QA_OK = ("rev", "two", "out")


@pytest.fixture
def studio(tmp_path, monkeypatch):
    root = tmp_path / "studios" / "acme"
    (root / "briefs").mkdir(parents=True)
    (root / "studio.yaml").write_text("name: Acme\nkind: brand\nlanguages: [en]\nplatforms: [tiktok]\n",
                                      encoding="utf-8")
    (root / "plan.yaml").write_text(PLAN, encoding="utf-8")
    (root / "briefs" / "briefed.md").write_text("# Бриф\n\n## 1. Тема\n**Briefed topic**\n", encoding="utf-8")
    (root / "briefs" / "loose.md").write_text("# Бриф\n\n## 1. Тема\n**A loose brief?**\n", encoding="utf-8")
    (root / "briefs" / "_TEMPLATE.md").write_text("**template**\n", encoding="utf-8")
    monkeypatch.setattr(jobs, "DIR", tmp_path / "jobs")
    ws = workspace.Workspace.at(root, id="acme", tools=workspace.ROOT / "tools")
    plan = {i["slug"]: i for i in batch.load(batch.plan_path(ws))["items"]}
    for slug in ("empty", "prod", "rev", "two", "out"):
        batch.create(ws, plan[slug])
    for slug in ("prod", "rev", "two", "out"):  # как будто Claude написал сценарий
        shutil.copytree(KIND_DEMOS / "short-hook", ws.project(slug), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("build", "logs", "project.yaml"))
        f = ws.project(slug) / "project.yaml"
        cfg = yaml.safe_load(f.read_text(encoding="utf-8"))
        demo = yaml.safe_load((KIND_DEMOS / "short-hook" / "project.yaml").read_text(encoding="utf-8"))
        cfg.update({k: demo[k] for k in ("title", "topic", "chapters", "brief") if k in demo})
        f.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
        (ws.project(slug) / "outline.md").write_text("# Plan\n\nch01 — 15 s.\n", encoding="utf-8")
    for slug in QA_OK:
        _finish(ws, slug)
    return ws


def _finish(ws, slug, verdict="PASS"):
    """Готовый ролик без рендера: финал каждого выхода, озвучка по текущему сценарию, отчёт QA новее финала."""
    for t in project.load(ws.project(slug)).targets():
        files = [(t.final_path(), "mp4"), (t.qa_dir / "report.md", f"# QA\n\nИтог: **{verdict}**\n")]
        if verdict == "PASS":  # озвучка по сценарию; у FAIL её нет — status не станет пересчитывать сцены
            files.insert(1, (t.build / "timeline.json", json.dumps({"src": source_hash(t)})))
        for f, text in files:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")


def _publish(ws, slug, out, date="2026-11-09 18:00", platform="tiktok"):
    f = ws.project(slug) / "published.yaml"
    recs = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else []
    recs.append({"out": out, "platform": platform, "url": f"https://www.tiktok.com/@acme/video/{len(recs) + 1}",
                 "date": date})
    f.write_text(yaml.safe_dump(recs), encoding="utf-8")


def _by_slug(ws):
    return {r["slug"]: r for r in C.rows(ws, today=TODAY)}


def test_stages_from_files(studio):
    r = _by_slug(studio)
    assert r["holiday-gift-guide"]["stage"] == "idea" and r["holiday-gift-guide"]["date"] is None
    assert r["late"]["stage"] == "idea" and "просрочен на 6 дн." in r["late"]["warn"]
    assert r["briefed"]["stage"] == "brief" and "briefs/briefed.md" in r["briefed"]["detail"]
    assert "через 2 дн., сценария нет" in r["briefed"]["warn"]
    assert r["empty"]["stage"] == "brief" and "нужно: 1 Бриф" in r["empty"]["detail"]
    assert r["prod"]["stage"] == "production" and r["prod"]["detail"] == "дальше: 4 Озвучка и тайминг"
    # без ревью у бренда QA ✅ — сразу «готов»; у двух выходов ни один не опубликован
    assert r["rev"]["stage"] == "ready" and "publish rev" in r["rev"]["detail"]
    assert r["two"]["stage"] == "ready" and r["two"]["platforms"] == ["tiktok", "instagram-reels"]
    assert r["out"]["stage"] == "ready" and "просрочен на 2 дн." in r["out"]["warn"]
    # брифы вне плана — стадия brief без даты; заготовка _TEMPLATE не ролик
    assert r["loose"]["stage"] == "brief" and r["loose"]["topic"] == "A loose brief?"
    assert "_TEMPLATE" not in r
    # порядок: по дате, без даты — в конце по стадии
    order = [x["slug"] for x in C.rows(studio, today=TODAY)]
    assert order[:2] == ["late", "out"] and order[-2:] == ["holiday-gift-guide", "loose"]


def test_queue_review_publish(studio):
    jobs.add(batch.job_argv(studio, {"slug": "prod"}), title="all prod")
    from studio.project import load
    rev = load(studio.project("rev"))
    c = review.add(rev, 1.0, "Logo is too small", sc=[{"chapter": "ch01", "id": "s01", "start": 0.0, "dur": 3.0}])
    _publish(studio, "two", "tiktok")
    _publish(studio, "out", None, date="2026-11-09 18:00")
    r = _by_slug(studio)
    assert r["prod"]["stage"] == "production" and "в очереди" in r["prod"]["detail"]
    assert r["rev"]["stage"] == "review" and "открытых комментариев 1" in r["rev"]["detail"]
    review.update(rev, c["id"], status="done")
    assert _by_slug(studio)["rev"]["stage"] == "review"  # закрыто, но версия не утверждена
    review.set_status(rev, "approved")
    assert _by_slug(studio)["rev"]["stage"] == "ready"
    assert r["two"]["stage"] == "ready" and "опубликовано 1/2 (tiktok)" in r["two"]["detail"]
    _publish(studio, "two", "instagram-reels", platform="instagram")
    two = _by_slug(studio)["two"]
    assert two["stage"] == "published" and two["date"] == dt.date(2026, 11, 9)
    out = r["out"]
    assert out["stage"] == "published" and out["date"] == dt.date(2026, 11, 9)
    assert out["warn"] == "по плану 2026-11-08"  # опубликован позже плана — без «просрочен»


def test_client_needs_approval_and_unplanned(studio):
    f = studio.root / "studio.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace("kind: brand", "kind: client"), encoding="utf-8")
    shutil.copytree(studio.project("rev"), studio.project("extra"))
    shutil.copytree(studio.project("rev"), studio.project("extra-demo"))  # демо стиля — не ролик
    _finish(studio, "extra")
    _finish(studio, "prod", verdict="FAIL")
    sc = studio.project("out") / "script" / "ch01.yaml"  # сценарий поправили после QA — снова производство
    sc.write_text(sc.read_text(encoding="utf-8").replace("Put the phone away.", "Put the phone down."), encoding="utf-8")
    r = _by_slug(studio)
    assert r["prod"]["stage"] == "production" and "QA ❌" in r["prod"]["detail"]
    assert r["out"]["stage"] == "production" and "4 Озвучка" in r["out"]["detail"]
    assert r["rev"]["stage"] == "review" and "клиент не утвердил" in r["rev"]["detail"]
    assert r["extra"]["from"] == "project" and r["extra"]["date"] is None and r["extra"]["platforms"] == ["tiktok"]
    assert "extra-demo" not in r


def test_batch_skips_ideas(studio, capsys):
    p = batch.load(batch.plan_path(studio))
    idea = next(i for i in p["items"] if i["slug"] == "holiday-gift-guide")
    assert batch.state(studio, idea, [])[0] == "idea"
    assert cli.main(["batch", "--plan", str(batch.plan_path(studio)), "--only", "holiday-gift-guide"]) == 0
    assert not studio.project("holiday-gift-guide").exists() and "💡" in capsys.readouterr().out
    bad = studio.root / "bad.yaml"
    bad.write_text("items:\n  - {topic: x, stage: ready}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="можно только idea"):
        batch.load(bad)


def test_command_filters_and_markdown(studio, capsys, monkeypatch):
    monkeypatch.setattr(workspace, "_current", studio)
    assert cli.main(["calendar"]) == 0
    out = capsys.readouterr().out
    assert "Календарь Acme" in out and "== 2026-11 ==" in out and "== без даты ==" in out
    assert "💡 идея 2 → 📝 бриф 3 → 🎬 производство 1" in out
    assert cli.main(["calendar", "--month", "2026-11", "--stage", "ready", "--md"]) == 0
    out = capsys.readouterr().out
    assert "rev" in out and "loose" not in out and "late" not in out
    md = (studio.root / "CALENDAR.md").read_text(encoding="utf-8")
    assert "## 2026-11" in md and "| Дата | Стадия |" in md and "**two** — Two outputs" in md
    assert cli.main(["calendar", "--from", "2026-12-01"]) == 0 and "пусто" in capsys.readouterr().out
    with pytest.raises(SystemExit, match="нет стадии shipped"):
        cli.main(["calendar", "--stage", "shipped"])
    with pytest.raises(SystemExit, match="ГГГГ-ММ"):
        cli.main(["calendar", "--month", "11.2026"])
