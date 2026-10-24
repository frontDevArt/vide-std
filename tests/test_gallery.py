"""P0.2: фикстура gallery — все шаблоны, 2 главы со стыком, vertical и horizontal, голос fake."""
import json

import numpy as np
import pytest
import yaml

from conftest import ROOT, make_gallery
from studio import cli, project, render, timing
from studio.templates import REGISTRY

FIXTURE = ROOT / "tests" / "fixtures" / "gallery"


@pytest.fixture(scope="module", params=["horizontal", "vertical"])
def voiced(request, tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("gallery") / request.param, request.param)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


def test_covers_every_template():
    # Новый шаблон без сцены в фикстуре — красный тест: golden (P0.4) и selftest (P0.5) его не увидят.
    used = set()
    for ch in yaml.safe_load((FIXTURE / "project.yaml").read_text(encoding="utf-8"))["chapters"]:
        data = yaml.safe_load((FIXTURE / "script" / f"{ch}.yaml").read_text(encoding="utf-8"))
        used |= {s["template"] for s in data["scenes"]}
    used = {REGISTRY.canonical(n) or n for n in used}  # в фикстуре — старые имена (алиасы)
    # commerce (P2.9) пришёл на этапе 2, где golden меняться не может; рисование проверяет test_commerce.py
    # (lab_anchor ≡ commerce.price_tag, листы fake-discounts). В фикстуру — вместе с ближайшей сменой golden.
    # media (ROADMAP C2) — шаблоны с файлами-ассетами; рисование и вёрстку во всех форматах проверяет test_media.py,
    # QA — демо типов (selftest --kinds). Галерея и golden каждого шаблона в 16:9 и 9:16 — ROADMAP C4.
    full = {n for n in REGISTRY.templates() if not n.startswith(("commerce.", "media."))}
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
