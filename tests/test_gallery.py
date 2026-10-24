"""P0.2: фикстура gallery — все шаблоны, 2 главы со стыком, vertical и horizontal, голос fake."""
import json

import numpy as np
import pytest
import yaml

from conftest import ROOT, make_gallery
from studio import cli, project, render, timing
from studio.templates import REGISTRY

FIXTURE = ROOT / "tests" / "fixtures" / "gallery"
LIBRARY = ROOT / "tests" / "fixtures" / "library"


@pytest.fixture(scope="module", params=["horizontal", "vertical"])
def voiced(request, tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("gallery") / request.param, request.param)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


def _used(fixture):
    used = set()
    for ch in yaml.safe_load((fixture / "project.yaml").read_text(encoding="utf-8"))["chapters"]:
        data = yaml.safe_load((fixture / "script" / f"{ch}.yaml").read_text(encoding="utf-8"))
        used |= {s["template"] for s in data["scenes"]}
    return {REGISTRY.canonical(n) or n for n in used}  # в фикстурах — и старые имена (алиасы)


def test_covers_every_template():
    # Новый шаблон без сцены в фикстурах — красный тест: golden (P0.4, C4), selftest (P0.5) и галерея
    # (python -m studio gallery) его не увидят. gallery — базовые и lab, library — kit, commerce, media (ROADMAP C4).
    used = _used(FIXTURE) | _used(LIBRARY)
    # кроме шаблонов на внешнем движке (REQUIRES, web.html — C6): их кадр зависит от сборки браузера, тест — test_web_html
    full = {n for n, c in REGISTRY.templates().items() if not getattr(c, "REQUIRES", None)}
    assert used == full, (full - used, used - full)


def test_validate_is_clean(tmp_path, capsys):
    assert cli.main(["validate", str(make_gallery(tmp_path / "g"))]) == 0
    out = capsys.readouterr().out
    assert "⚠️" not in out and "❌" not in out, out


def test_timeline(voiced):
    tl = json.loads((voiced.build / "timeline.json").read_text(encoding="utf-8"))
    assert tl["backend"] == "fake" and tl["size"] == list(project.FORMATS[voiced.cfg["format"]])
    assert [s["chapter"] for s in tl["scenes"]].count("ch01") == 8
    assert [s["chapter"] for s in tl["scenes"]].count("ch02") == 10
    assert all(s["words"] for s in tl["scenes"])  # таймкоды слов есть везде: триггеры at и караоке


def test_timing_does_not_depend_on_format(voiced, tmp_path):
    other = make_gallery(tmp_path / "g", "square")
    proj = project.load(other)
    timing.layout(proj, log=lambda *_: None)
    a = json.loads((voiced.build / "timeline.json").read_text(encoding="utf-8"))
    b = json.loads((proj.build / "timeline.json").read_text(encoding="utf-8"))
    assert [(s["start"], s["dur"]) for s in a["scenes"]] == [(s["start"], s["dur"]) for s in b["scenes"]]


def test_chapter_seam_carries_state(voiced):
    tl, _ = render.prepare(voiced)
    sc = {(s["chapter"], s["id"]): s for s in tl["scenes"]}
    seam = sc[("ch02", "s01")]
    assert seam["glow"]["from"] != seam["glow"]["to"]  # glow: ember — переход подсветки на стыке
    assert sc[("ch01", "s08")]["glow"]["to"] == seam["glow"]["from"]
    assert "hero" in str(sc[("ch01", "s03")]["state_in"])  # keep: [hero] из s02 переехал в s03


def test_every_scene_draws(voiced, capsys):
    # Каждая сцена рисует кадр в середине, без «слово-триггер не найдено» и не пустой фон.
    tl, ctx = render.prepare(voiced)
    size = project.FORMATS[voiced.cfg["format"]]
    for s in tl["scenes"]:
        tpl = render.make_template(ctx, s)
        img = render.frame(ctx, tpl, s, s["n_frames"] // 2, 40).convert("RGB")
        assert img.size == size
        assert np.asarray(img).std() > 3, s["id"]
    out = capsys.readouterr().out
    assert "⚠️" not in out, out
