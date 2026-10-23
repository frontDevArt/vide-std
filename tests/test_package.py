"""ROADMAP B5: пакет к выходу — обложка, description.md (главы, источники, хэштеги), checklist.md рядом с MP4."""
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from studio import cli, config, package, platforms, project

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"

REFS = ["Lally, P., van Jaarsveld, C., Potts, H., & Wardle, J. (2010). How are habits formed. EJSP.",
        "Gardner, B. (2012). Making health habitual. BJGP.",
        "YouGov. Habits survey. https://example.org/yougov"]


def _proj(dst, scenes=None, **cfg):
    shutil.copytree(FIXTURE, dst)
    p = dst / "project.yaml"
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    data.update(cfg)
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    if scenes:
        (dst / "script" / "ch01.yaml").write_text(
            yaml.safe_dump({"chapter": "ch01", "title": "Habits", "scenes": scenes}), encoding="utf-8")
    return project.load(dst)


SCENES = [{"id": "s01", "template": "statement", "params": {"text": "Habit",
                                                           "source": {"text": "Lally et al., 2010 · n = 96"}},
           "lines": ["People say | it takes three weeks to build a habit."]},
          {"id": "s02", "template": "statement",
           "params": {"text": "Myth", "source": {"text": "YouGov, 2024 · Gardner, 2012 · May 2024 – May 2025"},
                      "verdict": {"verdict": "myth"}},
           "lines": ["Sixty-six days, on average. | The verdict: myth."]},
          {"id": "s03", "template": "statement", "params": {"text": "x", "source": {"text": "Smith & Doe, 1999"}},
           "lines": ["One more line."]}]


def test_schema_and_platform_fields():
    assert config.check({"package": {"title": "t", "sources": [], "hashtags": [], "cover": {"at": 1},
                                     "by_output": {"tiktok": {}}}}) == []
    assert "package" not in config.DEFAULTS
    yt, tt = platforms.get("youtube"), platforms.get("tiktok")
    assert yt.chapters and yt.title_max == 100 and yt.cover_mb == 2 and not yt.ai_voice
    assert tt.tags_max == 5 and tt.text_max == 2200 and tt.ai_voice and not tt.chapters


def test_citations_and_sources(tmp_path):
    proj = _proj(tmp_path / "p", SCENES, package={"sources": REFS + ["Unused, A. (2001). Extra."]})
    assert [(w, y) for _, w, y in package.citations(proj)] == [
        ("lally", "2010"), ("yougov", "2024"), ("gardner", "2012"), ("smith", "1999")]
    lines, missing = package.sources(proj)
    assert lines[:3] == [REFS[0], REFS[2], REFS[1]]  # по порядку цитат; YouGov без года — по фамилии
    assert lines[3] == "Smith & Doe, 1999" and missing == ["Smith & Doe, 1999"]
    assert lines[4] == "Unused, A. (2001). Extra."  # длинный ролик: ссылку автора не теряем


def test_cut_sources_only_cited(tmp_path):
    proj = _proj(tmp_path / "p", SCENES[:1], package={"sources": REFS})
    proj.src = tmp_path / "src"  # нарезка: только процитированные, ссылки исходника — запасной пул
    (proj.src).mkdir()
    (proj.src / "project.yaml").write_text(yaml.safe_dump({"package": {"sources": ["Lally, P. (2010). Src."]}}),
                                           encoding="utf-8")
    proj.cfg["package"] = {}
    assert package.sources(proj) == (["Lally, P. (2010). Src."], [])


def test_chapters_rules(tmp_path):
    proj = _proj(tmp_path / "p")
    proj.chapters = [("ch01", {"title": "Intro"}), ("ch02", {"title": "Lab"}), ("ch03", {"title": "Short"}),
                     ("ch04", {"title": "End"})]
    sc = lambda ch, t: {"chapter": ch, "start": t}  # noqa: E731
    tl = {"duration": 100.0, "scenes": [sc("ch01", 0.4), sc("ch02", 30), sc("ch03", 60), sc("ch04", 65)]}
    chs, why = package.chapters(proj, tl)
    assert chs == [(0.0, "Intro"), (30, "Lab"), (65, "End")] and not why  # ch03 < 10 c — слита, первая — 0:00
    chs, why = package.chapters(proj, {"duration": 40.0, "scenes": [sc("ch01", 0), sc("ch02", 20)]})
    assert chs == [] and "трёх" in why
    assert package.tc(65) == "1:05" and package.tc(3725) == "1:02:05"


def test_hashtags_and_by_output(tmp_path):
    proj = _proj(tmp_path / "p", deliverables=["youtube", "tiktok"],
                 package={"title": "Main", "hashtags": ["psychology", "#habits", "habits", "a b"],
                          "by_output": {"tiktok": {"title": "TT"}}})
    tt = proj.output("tiktok")
    assert package.settings(tt)["title"] == "TT" and package.settings(proj.output("youtube"))["title"] == "Main"
    tags, extra = package.hashtags(package.settings(tt), platforms.get("tiktok"))
    assert tags == ["#psychology", "#habits", "#ab"] and extra == []
    tags, extra = package.hashtags({"hashtags": list("abcdef")}, platforms.get("tiktok"))
    assert len(tags) == 5 and extra == ["#f"]


def test_cover_template_from_brand(tmp_path):
    from studio import workspace
    (tmp_path / "projects").mkdir()
    (tmp_path / "brand").mkdir()
    (tmp_path / "brand" / "cover.yaml").write_text("text: {size: 0.2}\nshade: 0\n", encoding="utf-8")
    with workspace.use(tmp_path):
        proj = _proj(tmp_path / "projects" / "c")
        assert package.cover_template(proj) == package.COVER  # без style.brand — умолчание
        proj.cfg["style"]["brand"] = "brand"
        tpl = package.cover_template(proj)
        assert tpl["text"]["size"] == 0.2 and tpl["shade"] == 0 and tpl["text"]["upper"] is True


# --- сквозной прогон ----------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    dst = tmp_path_factory.mktemp("pk") / "p"
    _proj(dst, SCENES[:2], format="horizontal", deliverables=["youtube", "tiktok"],
          package={"title": "Does a habit take 21 days?", "description": "We checked the research.",
                   "sources": REFS, "hashtags": ["psychology", "habits"],
                   "cover": {"text": "21 DAYS?", "at": "s01"}})
    assert cli.main(["voice", str(dst)]) == 0
    assert cli.main(["render", str(dst), "--workers", "2"]) == 0
    assert cli.main(["assemble", str(dst)]) == 0
    return project.load(dst)


def test_package_files(built):
    assert cli.main(["package", str(built.root)]) == 0
    out = built.root / "output" / "p"
    names = sorted(p.name for p in out.iterdir())
    for o in ("youtube", "tiktok"):
        for suf in (".mp4", ".srt", ".vtt", ".cover.jpg", ".description.md", ".checklist.md"):
            assert f"{o}{suf}" in names
    assert Image.open(out / "youtube.cover.jpg").size == (1280, 720)  # обложка YouTube — профиль площадки
    assert Image.open(out / "tiktok.cover.jpg").size == (1080, 1920)  # TikTok — кадр ролика
    assert (out / "youtube.cover.jpg").stat().st_size < 2e6
    yt = (out / "youtube.description.md").read_text(encoding="utf-8")
    assert "Does a habit take 21 days?" in yt and "Sources:\n- " + REFS[0] in yt and "#psychology" not in yt
    assert "Главы не добавлены" in yt  # одна глава
    tt = (out / "tiktok.description.md").read_text(encoding="utf-8")
    assert "#psychology #habits" in tt and "## Подпись" in tt
    ck = (out / "tiktok.checklist.md").read_text(encoding="utf-8")
    assert "AI-generated content" in ck and "Субтитры вшиты" in ck and "QA: не запускался" in ck
    ck = (out / "youtube.checklist.md").read_text(encoding="utf-8")
    assert "Altered or synthetic content" in ck and "Загрузить субтитры `youtube.srt`" in ck


def test_package_errors(built, capsys):
    yt = built.output("youtube")
    yt.cfg["package"] = dict(yt.cfg["package"], title="x" * 101)
    errs, _ = package.build(yt, log=lambda *_: None)
    assert any("предел 100" in e for e in errs)
    assert "❌ название 101" in (built.root / "output" / "p" / "youtube.checklist.md").read_text(encoding="utf-8")


def test_project_without_deliverables_copies_final(tmp_path):
    proj = _proj(tmp_path / "q", SCENES[:1])
    assert cli.main(["voice", str(proj.root)]) == 0
    fin = proj.final_path()
    fin.write_bytes(b"mp4")
    fin.with_suffix(".srt").write_text("1\n", encoding="utf-8")
    errs, _ = package.build(project.load(proj.root), log=lambda *_: None)
    d = tmp_path / "q" / "output" / "q"
    assert (d / "q.mp4").read_bytes() == b"mp4" and (d / "q.srt").exists() and (d / "q.cover.jpg").exists()
    assert "по формату: tiktok" in (d / "q.checklist.md").read_text(encoding="utf-8")
    assert not errs
