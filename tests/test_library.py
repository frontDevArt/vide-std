"""ROADMAP C4: библиотека шаблонов kit, фикстура library, CSV графиков, режимы субтитров, галерея."""
import numpy as np
import pytest
import yaml

from studio import assets, cli, gallery, project, render, safezone, subs, timing, validate
from studio.packs import REGISTRY
from studio.packs.kit import chart
from studio.packs.lab.check import trigger_errors
from studio.selftest import make_library

KIT = {"kit.chart", "kit.timeline", "kit.steps", "kit.compare", "kit.map", "kit.quote", "kit.testimonial",
       "kit.lower_third", "kit.cta_end", "kit.chapter_bumper"}


def _laid(root):
    proj = project.load(root)
    timing.layout(proj, log=lambda *_a, **_k: None)
    return proj


def test_kit_registered_with_flat_aliases():
    assert KIT <= set(REGISTRY.templates())
    for full in KIT:
        assert REGISTRY.canonical(full.split(".", 1)[1]) == full
    assert REGISTRY.canonical("price_tag") == "commerce.price_tag"


def test_library_validates_clean(tmp_path, capsys):
    assert cli.main(["validate", str(make_library(tmp_path / "library"))]) == 0
    out = capsys.readouterr().out
    assert "⚠️" not in out and "❌" not in out, out


@pytest.mark.parametrize("fmt", ["horizontal", "vertical", "square", "portrait"])
def test_library_frames_in_zone(tmp_path, fmt):
    """Каждая сцена library рисует что-то, триггеры `at` найдены, контент — в безопасной зоне во всех форматах."""
    proj = _laid(make_library(tmp_path / "library", fmt))
    tl, ctx = render.prepare(proj)
    assert trigger_errors(tl["scenes"], REGISTRY) == []
    for s in tl["scenes"]:
        mid = render.frame(ctx, render.make_template(ctx, s), s, s["n_frames"] * 2 // 3, 40, alpha=True)
        assert (np.asarray(mid)[:, :, 3] > 40).mean() > 0.003, f"{s['id']}: пустой кадр"
    assert safezone.scan(proj) == [], [safezone.message(i) for i in safezone.scan(proj)]


def test_kit_word_triggers_checked(tmp_path):
    """Слово-триггер kit, которого нет в озвучке, — ошибка (как у lab), а не молча «сразу»."""
    root = make_library(tmp_path / "library")
    f = root / "script" / "ch01.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace('at: "grew"', 'at: "shrank"'), encoding="utf-8")
    proj = _laid(root)
    tl, _ = render.prepare(proj)
    errs = trigger_errors(tl["scenes"], REGISTRY)
    assert any("ch01/s02" in e and "shrank" in e for e in errs), errs


# ------------------------------------------------------------------ chart: данные
def test_parse_number():
    assert chart.parse_number("$1,234.5") == 1234.5
    assert chart.parse_number("12 %") == 12.0
    assert chart.parse_number("3,5") == 3.5          # дробная запятая
    assert chart.parse_number("12,480") == 12480.0   # разделитель тысяч
    assert chart.parse_number("n/a") is None


def test_read_csv(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("year;hours;note\n2019;3.1;a\n2020;4.40;b\nbad;x;c\n", encoding="utf-8")
    labels, values, dec, col = chart.read_csv(f)
    assert labels == ["2019", "2020"] and values == [3.1, 4.4] and dec == 2 and col == "hours"
    with pytest.raises(ValueError, match="нет столбца"):
        chart.read_csv(f, y="minutes")


def test_csv_is_an_asset(tmp_path):
    """CSV графика — ассет: в ключе рендера (новые данные — сцена перерисуется), validate требует запись с источником."""
    root = make_library(tmp_path / "library")
    assert assets.refs({"data": "assets/sales.csv"}) == ["assets/sales.csv"]
    proj = _laid(root)
    tl, _ = render.prepare(proj)
    key = {s["id"]: s["key"] for s in tl["scenes"] if s["chapter"] == "ch01"}
    (root / "assets" / "sales.csv").write_text("month,sales\nJan,1\nFeb,2\n", encoding="utf-8")
    tl2, _ = render.prepare(project.load(root))
    key2 = {s["id"]: s["key"] for s in tl2["scenes"] if s["chapter"] == "ch01"}
    assert key2["s02"] != key["s02"] and key2["s03"] == key["s03"]
    reg = root / "assets.yaml"
    d = yaml.safe_load(reg.read_text(encoding="utf-8"))
    d["assets"] = [e for e in d["assets"] if e["file"] != "assets/sales.csv"]
    reg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    rep = validate.check(project.load(root))
    assert any("sales.csv" in w for w in rep.warns)


def test_chart_pie_shares_and_highlight(tmp_path):
    proj = _laid(make_library(tmp_path / "library"))
    tl, ctx = render.prepare(proj)
    s = next(x for x in tl["scenes"] if x["chapter"] == "ch01" and x["id"] == "s04")
    tpl = render.make_template(ctx, s)
    assert tpl.labels[tpl.hl] == "Video" and abs(sum(tpl.share) - 1) < 1e-9


# ------------------------------------------------------------------ субтитры
def test_subtitles_style_tiktok(tmp_path):
    """subtitles.style: tiktok без бренд-кита — крупнее, выше, рисуются режимом tiktok; без ключа — как раньше."""
    plain = project.load(make_library(tmp_path / "a" / "library", "vertical"))
    tik = project.load(make_library(tmp_path / "b" / "library", "vertical", "tiktok"))
    assert "subs" not in plain.cfg["style"] and subs.mode(plain) is None
    assert subs.mode(tik) == "tiktok" and subs.font_size(tik) > subs.font_size(plain)
    assert subs.band_top(tik) < subs.band_top(plain)
    timing.layout(tik, log=lambda *_a, **_k: None)
    _, ctx = render.prepare(tik)
    assert ctx["style"].subs == "tiktok"


def test_subtitles_style_validated(tmp_path):
    rep = validate.check(project.load(make_library(tmp_path / "library", subs="huge")))
    assert any("subtitles.style" in e for e in rep.errs)


# ------------------------------------------------------------------ галерея
def test_gallery_page():
    """Страница галереи: карточка на каждый шаблон, кадры в каждом формате (на готовых записях, без съёмки)."""
    names = list(REGISTRY.templates())
    entries = [{"template": n, "fixture": "x", "scene": "ch01/s01", "format": f, "dur": 1.0,
                "frames": [f"img/{f}/{n}-{i}.jpg" for i in range(5)]}
               for n in names for f in ("horizontal", "vertical")]
    page = gallery.render_html(entries, ["horizontal", "vertical"])
    for n in names:
        assert f'id="{n}"' in page
    assert page.count('class="shot f-vertical"') == len(names)
    assert gallery.absent(entries) == []
    assert "Нет в галерее" in gallery.render_html(entries[2:], ["horizontal", "vertical"])


def test_gallery_shoot_one_job(tmp_path):
    """Воркер галереи снимает сцены фикстуры: 5 кадров на сцену, файлы на месте, шаблоны — полные имена."""
    res = gallery._shoot(("library", "square", None, str(tmp_path / "img"), str(tmp_path / "work")))
    assert {e["template"] for e in res} >= KIT
    for e in res:
        assert len(e["frames"]) == len(gallery.FRACS)
        assert all((tmp_path / f).is_file() for f in e["frames"])
    sub = gallery._shoot(("library", "vertical", "tiktok", str(tmp_path / "img"), str(tmp_path / "work")))
    assert [e["template"] for e in sub] == ["subtitles.tiktok"]
