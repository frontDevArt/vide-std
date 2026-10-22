"""P1.4 (B4, B5, B6): стиль — палитра, настроение и шрифт — применяется одной функцией и везде одинаково."""
import subprocess
from types import SimpleNamespace

import pytest
from conftest import make_gallery

from studio import gfx as G
from studio import project, qa, render, timing


@pytest.fixture(autouse=True)
def neon_after():
    yield
    G.apply_style({"palette": "neon"})  # стиль — глобальный: не протекает в другие тесты


def _sub_font_path(proj):
    from studio import subs as S
    return G.font(S.font_size(proj), "bold").path


def test_qa_measures_subs_with_render_font(tmp_path):
    # B4: QA мерил ширину субтитров шрифтом без стиля (Arial/Inter), а рисуются они шрифтом пресета (Manrope у lab)
    proj = project.load(make_gallery(tmp_path / "g"))
    timing.layout(proj, log=lambda *_: None)
    render.prepare(proj)
    drawn = _sub_font_path(proj)
    assert drawn.endswith("Manrope-VF.ttf")
    G.apply_style({"palette": "neon"})  # свежий процесс `qa`: стиль по умолчанию
    with pytest.raises(SystemExit):  # финала нет — но стиль уже применён
        qa.run(proj, log=lambda *_: None)
    assert _sub_font_path(proj) == drawn


def test_layout_applies_font_family(tmp_path):
    # B5: layout применял палитру, но не style.font — перенос субтитров считался другим шрифтом
    root = make_gallery(tmp_path / "g")
    p = root / "project.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("palette: lab", "palette: neon\n  font: Some Font"),
                 encoding="utf-8")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    assert G.FONT_FAMILY == "Some Font"


def test_font_file_follows_family(tmp_path, monkeypatch):
    # B6: _font_file кэшировался по весу — смена семейства в одном процессе не действовала
    files = {}
    for fam in ("Fam A", "Fam B"):
        files[fam] = tmp_path / f"{fam}.ttf"
        files[fam].write_bytes(b"")
    monkeypatch.delenv("STUDIO_FONT_BOLD", raising=False)

    def fc_match(cmd, **kw):
        fam = cmd[-1].split(":")[0]
        return SimpleNamespace(returncode=0, stdout=str(files[fam]))

    monkeypatch.setattr(subprocess, "run", fc_match)
    G.apply_style({"palette": "neon", "font": "Fam A"})
    assert G._font_file("bold") == str(files["Fam A"])
    G.apply_style({"palette": "neon", "font": "Fam B"})
    assert G._font_file("bold") == str(files["Fam B"])
