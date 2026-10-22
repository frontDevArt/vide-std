"""P1.10: QA вёрстки — контент сцены (без фона и субтитров) должен держаться в полях кадра (по умолчанию 4 %).
Пока только ⚠️: вертикаль `lab_*` не свёрстана (STYLE §12), после ROADMAP B2 станет ❌."""
import pytest

from conftest import make_gallery
from studio import cli, project, safezone, timing


@pytest.fixture(scope="module", params=["horizontal", "vertical"])
def voiced(request, tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("sz") / request.param, request.param)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


def _by_id(issues):
    return {(i["chapter"], i["id"]): i for i in issues}


def test_vertical_lab_chapter_warns(voiced):
    issues = _by_id(safezone.scan(voiced))
    if voiced.cfg["format"] == "horizontal":
        assert issues == {}  # горизонталь свёрстана: всё в полях
        return
    ch = issues[("ch01", "s01")]
    assert ch["template"] == "lab_chapter" and "справа" in ch["bad"]
    assert ch["margins"]["right"] < 0.04
    assert all(s[0] == "ch01" for s in issues)  # базовые шаблоны (ch02) в вертикали в полях


def test_margin_from_config(voiced):
    # поле 0 — ничего не нарушено; огромное — нарушено везде
    assert safezone.scan(voiced, margin=0.0) == []
    assert len(safezone.scan(voiced, margin=0.45)) == 18


def test_message(voiced):
    issues = safezone.scan(voiced)
    if not issues:
        pytest.skip("горизонталь чистая")
    m = safezone.message(issues[0], 0.04)
    assert m.startswith("ch01/s01 lab_chapter: контент у края — справа 0 %") and "поле 4 %" in m


def test_stills_reports_warning(voiced, capsys):
    cli.main(["stills", str(voiced.root), "--chapter", "ch01"])
    out = capsys.readouterr().out
    if voiced.cfg["format"] == "vertical":
        assert "⚠️  ch01/s01 lab_chapter: контент у края" in out
    else:
        assert "⚠️" not in out


def test_qa_check_is_warning_only(voiced):
    res = []
    safezone.qa_check(voiced, lambda st, name, det: res.append((st, name, det)))
    (st, name, det), = res
    assert name == "Контент в безопасной зоне"
    assert st == ("WARN" if voiced.cfg["format"] == "vertical" else "PASS")
