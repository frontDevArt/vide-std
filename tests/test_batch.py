"""ROADMAP D2: контент-план студии → проекты серии → очередь рендеров (studio/batch.py, команда batch).
Рендера нет: задачи очереди — заглушка; живой прогон серии — в docs/ROADMAP.md (D2, «Сделано»)."""
import shutil
import sys

import pytest
import yaml

from studio import batch, cli, jobs, workspace
from studio.selftest import KIND_DEMOS

PLAN = """
series: autumn
defaults: {kind: short-hook, platforms: [tiktok], duration: 15, lang: en, tts: fake}
items:
  - {date: 2026-11-03, topic: "Brew in three minutes", slug: brew}
  - {date: 2026-11-05, topic: "Lamp sale", slug: lamp, kind: promo, platforms: [tiktok, instagram-reels]}
  - {date: 2026-12-01, topic: "Winter preview"}
"""


@pytest.fixture
def studio(tmp_path, monkeypatch):
    root = tmp_path / "studios" / "acme"
    root.mkdir(parents=True)
    (root / "studio.yaml").write_text("name: Acme\nkind: brand\nlanguages: [en]\nplatforms: [tiktok]\n",
                                      encoding="utf-8")
    (root / "plan.yaml").write_text(PLAN, encoding="utf-8")
    monkeypatch.setattr(jobs, "DIR", tmp_path / "jobs")
    ws = workspace.Workspace.at(root, id="acme", tools=workspace.ROOT / "tools")
    return ws


def write_script(ws, slug, kind):
    """Как будто Claude написал сценарий (/new-video): project.yaml и script/ из демо типа."""
    dst = ws.project(slug)
    shutil.copytree(KIND_DEMOS / kind, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build", "logs"))


def test_load_defaults_and_slugs(studio):
    p = batch.load(batch.plan_path(studio))
    assert p["series"] == "autumn" and [i["slug"] for i in p["items"]] == ["brew", "lamp", "winter-preview"]
    lamp = p["items"][1]
    assert (lamp["kind"], lamp["platforms"], lamp["duration"]) == ("promo", ["tiktok", "instagram-reels"], 15)
    assert str(p["items"][0]["date"]) == "2026-11-03"
    import datetime as dt
    assert [i["slug"] for i in batch.select(p["items"], until=dt.date(2026, 11, 30))] == ["brew", "lamp"]
    assert [i["slug"] for i in batch.select(p["items"], only={"lamp"})] == ["lamp"]


def test_load_reports_all_errors(tmp_path):
    f = tmp_path / "plan.yaml"
    f.write_text("items:\n  - {topic: a, slug: x, colour: red}\n  - {slug: y}\n  - {topic: b, slug: x}\n"
                 "  - {topic: c, platforms: [tiktk], kind: nope, date: 'next week'}\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        batch.load(f)
    msg = str(e.value)
    for part in ("неизвестные поля colour", "нет topic", "slug x повторяется", "tiktk", "нет типа nope",
                 "нужно ГГГГ-ММ-ДД"):
        assert part in msg, part


def test_create_and_states(studio):
    p = batch.load(batch.plan_path(studio))
    brew, lamp, _ = p["items"]
    assert batch.state(studio, brew, [])[0] == "new"
    batch.create(studio, lamp)
    cfg = yaml.safe_load(studio.project("lamp").joinpath("project.yaml").read_text(encoding="utf-8"))
    assert (cfg["kind"], cfg["platform"], cfg["deliverables"], cfg["tts"]["backend"], cfg["target_duration"]) == \
        ("promo", "tiktok", ["tiktok", "instagram-reels"], "fake", 15)
    code, det = batch.state(studio, lamp, [])
    assert code == "draft" and "/new-video" in det
    batch.create(studio, brew)
    write_script(studio, "brew", "short-hook")
    assert batch.state(studio, brew, [])[0] == "ready"
    argv = batch.job_argv(studio, brew, yes=True, workers=2)
    assert argv[0] == "all" and argv[1] == str(studio.project("brew").resolve()) and argv[2:] == \
        ["--yes", "--workers", "2"]
    j, _ = jobs.add(argv)
    assert batch.state(studio, brew)[0] == "queued"
    j.update(status="failed", rc=1)
    jobs._save(j)
    code, det = batch.state(studio, brew)
    assert code == "failed" and "лог" in det


def test_batch_command(studio, monkeypatch, capsys):
    """`batch`: создаёт проекты, готовые — в очередь; `--run` выполняет очередь; `--list` ничего не меняет."""
    plan = str(batch.plan_path(studio))
    assert cli.main(["batch", "--plan", plan, "--list"]) == 0
    assert workspace.projects(studio) == []  # --list ничего не создаёт
    assert cli.main(["batch", "--plan", plan, "--until", "2026-11-30"]) == 0
    assert {p.name for p in workspace.projects(studio)} == {"brew", "lamp"}  # декабрьский — позже
    assert jobs.load() == []  # сценариев ещё нет
    write_script(studio, "brew", "short-hook")
    write_script(studio, "lamp", "promo")
    assert cli.main(["batch", "--plan", plan, "--until", "2026-11-30"]) == 0
    q = jobs.load()
    assert [j["title"] for j in q] == ["all brew", "all lamp"] and all(j["status"] == "queued" for j in q)
    assert cli.main(["batch", "--plan", plan, "--until", "2026-11-30"]) == 0
    assert len(jobs.load()) == 2  # повторный запуск не дублирует задачи
    ran = []
    monkeypatch.setattr(jobs, "command", lambda argv: ran.append(argv) or [sys.executable, "-c", "pass"])
    capsys.readouterr()
    assert cli.main(["batch", "--plan", plan, "--run"]) == 0
    assert [a[1] for a in ran] == [str(studio.project(s).resolve()) for s in ("brew", "lamp")]
    assert all(j["status"] == "done" for j in jobs.load())
    out = capsys.readouterr().out
    assert "✍️  2026-12-01  winter-preview" in out and "Серия autumn (Acme)" in out  # создан, ждёт сценария
