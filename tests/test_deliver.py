"""ROADMAP D5: версии и сдача — output/<slug>/vN/, manifest.json, CHANGELOG.md проекта, compare.jpg, архив для клиента."""
import json
import shutil
import zipfile
from pathlib import Path

import pytest
import yaml

from studio import cli, deliver, project, review

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"

SCENES = [{"id": "s01", "template": "statement", "params": {"text": "Habit"},
           "lines": ["People say it takes three weeks to build a habit."]},
          {"id": "s02", "template": "statement", "params": {"text": "Myth"},
           "lines": ["Sixty-six days, on average."]}]


def _write(dst, scenes):
    (dst / "script" / "ch01.yaml").write_text(
        yaml.safe_dump({"chapter": "ch01", "title": "Habits", "scenes": scenes}), encoding="utf-8")


def _build(dst):
    for cmd in (["voice", str(dst)], ["render", str(dst), "--workers", "2"], ["assemble", str(dst)]):
        assert cli.main(cmd) == 0
    proj = project.load(dst)
    (proj.qa_dir / "report.md").write_text("# QA\n\nИтог: **PASS**\n", encoding="utf-8")  # qa целиком — долго
    return proj


@pytest.fixture(scope="module")
def two_versions(tmp_path_factory):
    dst = tmp_path_factory.mktemp("dl") / "p"
    shutil.copytree(FIXTURE, dst)
    data = yaml.safe_load((dst / "project.yaml").read_text(encoding="utf-8"))
    data.update(format="horizontal", package={"title": "Habits", "description": "Checked."})
    (dst / "project.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    _write(dst, SCENES)
    proj = _build(dst)
    (proj.qa_dir / "report.md").unlink()
    gate = deliver.deliver(proj, log=lambda *_: None)  # QA не запускался — версии нет
    (proj.qa_dir / "report.md").write_text("Итог: **PASS**\n", encoding="utf-8")
    v1 = deliver.deliver(proj, note="Первая сдача клиенту.", log=lambda *_: None)
    v1_mp4 = (deliver.vdir(proj, 1) / "p.mp4").read_bytes()
    # ревью клиента: комментарий к s02 → правка входа → пересборка → комментарий закрыт, версия утверждена
    c = review.add(proj, review.scenes(proj)[1]["start"] + 0.3, "Слово крупнее и другое: Truth")
    assert c["scene"] == "s02"
    scenes = [dict(s) for s in SCENES]
    scenes[1] = dict(scenes[1], params={"text": "Truth"})
    _write(dst, scenes)
    proj = _build(dst)
    review.update(proj, c["id"], status="done")
    review.set_status(proj, "approved")
    v2 = deliver.deliver(proj, log=lambda *_: None)
    return proj, gate, v1, v2, v1_mp4, c


def test_gate_blocks_without_qa(two_versions):
    proj, gate, v1, v2, *_ = two_versions
    assert gate is None and (v1, v2) == (1, 2) and deliver.versions(proj) == [1, 2]


def test_versions_side_by_side(two_versions):
    proj, *_, v1_mp4, c = two_versions
    out = proj.output_dir()
    for n in (1, 2):
        names = {p.name for p in deliver.vdir(proj, n).iterdir()}
        assert {"p.mp4", "p.srt", "p.cover.jpg", "p.description.md", "p.checklist.md", "manifest.json",
                "CHANGELOG.md"} <= names
        with zipfile.ZipFile(out / f"p-v{n}.zip") as z:
            zn = set(z.namelist())
        assert f"p-v{n}/p.mp4" in zn and f"p-v{n}/CHANGELOG.md" in zn and f"p-v{n}/manifest.json" not in zn
    assert (deliver.vdir(proj, 1) / "p.mp4").read_bytes() == v1_mp4  # v1 не перезаписана сборкой v2
    assert (deliver.vdir(proj, 2) / "p.mp4").read_bytes() != v1_mp4
    assert (deliver.vdir(proj, 2) / "compare.jpg").exists() and not (deliver.vdir(proj, 1) / "compare.jpg").exists()


def test_changelog_shows_difference(two_versions):
    proj, *_, c = two_versions
    log = (proj.root / "CHANGELOG.md").read_text(encoding="utf-8")
    assert log.startswith("# Изменения по версиям")
    assert log.index("## v2") < log.index("## v1")  # новые сверху
    v2 = log[log.index("## v2"):log.index("## v1")]
    assert f"[{c['id']}]" in v2 and "Truth" in v2 and "ch01/s02" in v2
    assert "Сцены изменены (1): ch01/s02" in v2 and "p.mp4 — изменён" in v2 and "compare.jpg" in v2
    assert "ch01/s01" not in v2.split("Сцены изменены")[1].split("\n")[0]
    v1 = log[log.index("## v1"):]
    assert "Первая сдача клиенту." in v1 and "Первая версия: 2 сцен" in v1
    m2 = json.loads((deliver.vdir(proj, 2) / "manifest.json").read_text(encoding="utf-8"))
    assert m2["version"] == 2 and not m2["forced"] and [x["id"] for x in m2["comments"]] == [c["id"]]


def test_list_and_diff_cli(two_versions, capsys):
    proj, *_ = two_versions
    assert cli.main(["deliver", str(proj.root), "--list"]) == 0
    out = capsys.readouterr().out
    assert "v1 —" in out and "v2 —" in out and "Сцены изменены (1): ch01/s02" in out
    assert cli.main(["deliver", str(proj.root), "--diff", "v1", "v2"]) == 0
    assert "ch01/s02" in capsys.readouterr().out
    assert cli.main(["deliver", str(proj.root), "--diff", "v1", "v2"]) == 0
    with pytest.raises(SystemExit):
        cli.main(["deliver", str(proj.root), "--diff", "v1", "v9"])


def test_force_marks_version(two_versions, tmp_path):
    proj, *_ = two_versions
    (proj.qa_dir / "report.md").write_text("Итог: **FAIL**\n", encoding="utf-8")
    try:
        assert cli.main(["deliver", str(proj.root)]) == 1
        assert deliver.versions(proj) == [1, 2]
        n = deliver.deliver(proj, force=True, log=lambda *_: None)
        m = deliver.manifest(proj, n)
        assert n == 3 and any("QA: FAIL" in e for e in m["forced"])
        log = (proj.root / "CHANGELOG.md").read_text(encoding="utf-8")
        v3 = log[:log.index("## v2")]
        assert "⚠️ Сдано с `--force`: QA: FAIL" in v3 and "- Файлы: p.checklist.md — изменён" in v3  # видео то же
    finally:
        (proj.qa_dir / "report.md").write_text("Итог: **PASS**\n", encoding="utf-8")
        shutil.rmtree(deliver.vdir(proj, 3), ignore_errors=True)


# --- без рендера ---------------------------------------------------------------------------------------------------

def _man(v, scenes, dur=10.0, files=None, cfg=None, comments=()):
    return {"version": v, "duration": dur, "files": files or {}, "cfg": cfg or {"style": "a"},
            "scenes": {k: {"hash": h, "start": 0, "dur": 1} for k, h in scenes.items()}, "comments": list(comments)}


def test_diff_rules():
    a = _man(1, {"ch01/s01": "x", "ch01/s02": "y"}, files={"p.mp4": {"sha1": "1"}, "p.srt": {"sha1": "s"}})
    b = _man(2, {"ch01/s01": "x", "ch01/s02": "z", "ch01/s03": "n"}, dur=12.5, cfg={"style": "b"},
             files={"p.mp4": {"sha1": "2"}, "p.cover.jpg": {"sha1": "c"}},
             comments=[{"id": "c1", "t": 3, "scene": "ch01/s02", "text": "крупнее"}])
    d = deliver.diff(a, b)
    assert d["changed"] == ["ch01/s02"] and d["added"] == ["ch01/s03"] and d["removed"] == []
    assert d["cfg"] == ["style"] and d["duration"] == (10.0, 12.5)
    assert d["files"] == {"p.mp4": "изменён", "p.cover.jpg": "новый", "p.srt": "удалён"}
    text = "\n".join(deliver.summary(d))
    assert "[c1] 0:03.0 ch01/s02: крупнее" in text and "0:10.0 → 0:12.5 (+2.5 с)" in text
    c = _man(3, {"ch01/s01": "x"}, dur=12.5, cfg={"style": "b"}, comments=b["comments"])
    d2 = deliver.diff(b, c)
    assert d2["removed"] == ["ch01/s02", "ch01/s03"] and d2["comments"] == []  # c1 закрыт ещё в v2
    assert deliver.summary(deliver.diff(c, c)) == ["- Отличий нет: та же сборка."]


def test_changelog_keeps_user_notes(tmp_path):
    proj = type("P", (), {"root": tmp_path, "slug": "p"})()
    (tmp_path / "CHANGELOG.md").write_text("# Мой журнал\n\nЗаметка руками.\n", encoding="utf-8")
    deliver._changelog(proj, 1, {"date": "d1"}, ["- a"])
    deliver._changelog(proj, 2, {"date": "d2", "note": "n2"}, ["- b"])
    t = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert t.startswith("# Мой журнал\n\nЗаметка руками.")
    assert t.index("## v2 — d2") < t.index("## v1 — d1") and "n2" in t
