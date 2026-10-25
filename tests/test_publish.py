"""ROADMAP E1: публикация вручную — карточка загрузки, ворота, отметка в published.yaml, --list, status."""
import shutil
from pathlib import Path

import pytest
import yaml

from studio import cli, deliver, project, publish, status

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
SCENES = [{"id": "s01", "template": "statement", "params": {"text": "Habit"},
           "lines": ["People say it takes three weeks to build a habit."]}]


def _pass(t):
    t.qa_dir.mkdir(parents=True, exist_ok=True)
    (t.qa_dir / "report.md").write_text("# QA\n\nИтог: **PASS**\n", encoding="utf-8")  # qa целиком — долго


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dst = tmp_path_factory.mktemp("pub") / "p"
    shutil.copytree(FIXTURE, dst)
    data = yaml.safe_load((dst / "project.yaml").read_text(encoding="utf-8"))
    data.update(format="horizontal", deliverables=["youtube", "tiktok"],
                package={"title": "Habits", "description": "Checked.", "hashtags": ["habits"]})
    (dst / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (dst / "script" / "ch01.yaml").write_text(
        yaml.safe_dump({"chapter": "ch01", "title": "Habits", "scenes": SCENES}), encoding="utf-8")
    for cmd in (["voice", str(dst)], ["render", str(dst), "--workers", "2"], ["assemble", str(dst)]):
        assert cli.main(cmd) == 0
    return project.load(dst)


def test_card_gates_without_qa(built, capsys):
    assert cli.main(["publish", str(built.root), "--out", "youtube"]) == 1  # QA не запускался
    out = capsys.readouterr().out
    assert "❌ QA: не запускался" in out and "Не публиковать" in out
    assert not publish.path(built).exists()
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done",
                     "--url", "https://youtu.be/abc"]) == 1
    assert not publish.path(built).exists()  # непроверенное не отмечается


def test_card_and_record(built, capsys):
    for o in ("youtube", "tiktok"):
        _pass(built.output(o))
    assert cli.main(["publish", str(built.root)]) == 0
    out = capsys.readouterr().out
    assert "studio.youtube.com" in out and "tiktokstudio/upload" in out
    assert "youtube.cover.jpg" in out and "youtube.srt" in out and "Altered or synthetic content" in out
    assert "Название: Habits" in out and "youtube.checklist.md" in out and "--done --url" in out
    # сданная версия: запись ссылается на неё по sha1 файла
    assert deliver.deliver(built, log=lambda *_: None) == 1
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done", "--url",
                     "https://www.youtube.com/watch?v=abc", "--at", "2026-10-25 18:00", "--note", "первый"]) == 0
    recs = publish.load(built)
    assert len(recs) == 1
    r = recs[0]
    assert (r["out"], r["platform"], r["date"], r["version"], r["file"], r["note"]) == \
        ("youtube", "youtube", "2026-10-25 18:00", 1, "youtube.mp4", "первый")
    assert r["sha1"] and r["duration"] > 0 and "forced" not in r
    assert publish.path(built).read_text(encoding="utf-8").startswith("# Публикации проекта")
    # та же ссылка — обновление, а не дубль
    assert cli.main(["publish", str(built.root), "--out", "youtube", "--done", "--url",
                     "https://www.youtube.com/watch?v=abc", "--at", "2026-10-25 19:00"]) == 0
    assert [x["date"] for x in publish.load(built)] == ["2026-10-25 19:00"]
    capsys.readouterr()
    assert cli.main(["publish", str(built.root), "--out", "youtube"]) == 0
    assert "Уже опубликовано: 2026-10-25 19:00" in capsys.readouterr().out


def test_record_checks_url_and_platform(built, capsys):
    tt = built.output("tiktok")
    _pass(tt)
    with pytest.raises(SystemExit, match="https://"):
        publish.record(tt, "tiktok.com/@me/video/1", log=lambda *_: None)
    with pytest.raises(SystemExit, match="ГГГГ-ММ-ДД"):
        publish.record(tt, "https://www.tiktok.com/@me/video/1", at="завтра", log=lambda *_: None)
    assert publish.record(tt, "https://youtu.be/x", log=lambda *_: None) is None  # ссылка не той площадки
    with pytest.raises(SystemExit, match="--out"):  # два выхода — какой опубликован, сказать явно
        cli.main(["publish", str(built.root), "--done", "--url", "https://www.tiktok.com/@me/video/1"])
    r = publish.record(tt, "https://youtu.be/x", force=True, log=lambda *_: None)
    assert r["forced"] and "TikTok" in r["forced"][0]
    r = publish.record(tt, "https://www.tiktok.com/@me/video/1", log=lambda *_: None)
    assert r["version"] == 1 and r["platform"] == "tiktok"


def test_list_and_status(built, capsys):
    capsys.readouterr()
    assert cli.main(["publish", str(built.root), "--list"]) == 0
    out = capsys.readouterr().out
    assert "youtube → youtube: https://www.youtube.com/watch?v=abc (v1)" in out and "⚠️ --force" in out
    status.report(built)
    assert "Публикация: youtube 2026-10-25" in capsys.readouterr().out


def test_status_unpublished(tmp_path, capsys):
    shutil.copytree(FIXTURE, tmp_path / "p")
    assert publish.summary(project.load(tmp_path / "p")).startswith("не опубликован")
