"""P1.10 + ROADMAP B2: QA вёрстки — контент сцены (без фона и субтитров) держится в полях кадра (по умолчанию 4 %).
С B2 шаблоны верстаются в сетке безопасной зоны (`Template.safe`), галерея чиста в 16:9, 9:16 и 4:5, нарушение — ❌."""
import pytest

from conftest import make_gallery
from studio import cli, platforms, project, render, safezone, timing


def _voiced(root, **cfg):
    if cfg:
        p = root / "project.yaml"
        p.write_text(p.read_text(encoding="utf-8") + "".join(f"\n{k}: {v}\n" for k, v in cfg.items()), encoding="utf-8")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


@pytest.fixture(scope="module", params=["horizontal", "vertical", "portrait"])
def voiced(request, tmp_path_factory):
    return _voiced(make_gallery(tmp_path_factory.mktemp("sz") / request.param, request.param))


def test_gallery_in_safe_zone(voiced):
    assert safezone.scan(voiced) == []  # B2: все 18 шаблонов в полях 4 % в любом формате галереи


def test_margin_from_config(voiced):
    # поле 0 — ничего не нарушено; огромное — нарушено везде
    assert safezone.scan(voiced, margin=0.0) == []
    assert len(safezone.scan(voiced, margin=0.45)) == 18


def test_message():
    i = {"chapter": "ch01", "id": "s01", "template": "lab_chapter", "bad": ["справа"], "ui": [],
         "margins": {"left": 0.3, "top": 0.4, "right": 0.0, "bottom": 0.1}}
    m = safezone.message(i, 0.04)
    assert m == "ch01/s01 lab_chapter: контент у края — справа 0 % (поле 4 %)"


def test_stills_reports(voiced, capsys):
    cli.main(["stills", str(voiced.root), "--chapter", "ch01"])
    assert "❌" not in capsys.readouterr().out


def test_qa_check_fails(voiced):
    res = []
    safezone.qa_check(voiced, lambda st, name, det: res.append((st, name, det)))
    assert res == [("PASS", "Контент в безопасной зоне", safezone._label(voiced))]
    voiced.cfg["qa"]["safe_margin"] = 0.3  # поле шире, чем держат телефонные шаблоны
    try:
        res.clear()
        safezone.qa_check(voiced, lambda st, name, det: res.append((st, name, det)))
    finally:
        voiced.cfg["qa"]["safe_margin"] = 0.04
    (st, name, det), = res
    assert st == "FAIL" and "контент у края" in det


# --- сетка вёрстки (B2) ------------------------------------------------------------------------------------------

def test_layout_zone():
    lz = platforms.layout_zone
    assert lz({"format": "horizontal"}) == {"top": 0.04, "bottom": 0.04, "left": 0.04, "right": 0.04}
    # 9:16 без площадки верстается по TikTok: колонка кнопок (с 0,86 ширины) — в симметричных боковых полях
    v = lz({"format": "vertical"})
    assert (v["top"], v["bottom"]) == (0.08, 0.2) and v["left"] == v["right"] == pytest.approx(0.14)
    assert lz({"format": "portrait"}) == {"top": 0.04, "bottom": 0.075, "left": 0.09, "right": 0.09}
    assert lz({"format": "vertical", "platform": "instagram-reels"})["bottom"] == 0.35
    assert lz({"format": "square", "qa": {"safe_margin": 0.1}})["top"] == 0.1  # не меньше qa.safe_margin


def test_template_safe_and_area(voiced):
    tl, ctx = render.prepare(voiced)
    s = next(s for s in tl["scenes"] if s["template"] == "lab_hero_stack")
    tpl = render.make_template(ctx, s)
    W, H, z = ctx["W"], ctx["H"], ctx["safe"]
    e = 0.01 * min(W, H)
    assert tpl.safe.x0 == pytest.approx(z["left"] * W + e) and tpl.safe.y1 == pytest.approx(H * (1 - z["bottom"]) - e)
    assert tpl.area.y1 <= tpl.safe.y1 and tpl.area.y1 <= ctx["subs_top"] * H  # тело — выше полосы субтитров
    assert tpl.wide == (W > H)


def test_scene_key_follows_zone(tmp_path):
    a = _voiced(make_gallery(tmp_path / "a", "vertical"))
    b = _voiced(make_gallery(tmp_path / "b", "vertical"), platform="instagram-reels")
    ka = [s["key"] for s in render.prepare(a)[0]["scenes"]]
    kb = [s["key"] for s in render.prepare(b)[0]["scenes"]]
    assert all(x != y for x, y in zip(ka, kb))  # другая зона — другая вёрстка — свой кэш


@pytest.mark.parametrize("fmt,plat", [("vertical", "tiktok"), ("vertical", "instagram-reels"),
                                      ("portrait", "instagram-feed")])
def test_lab_follows_platform_zone(tmp_path, fmt, plat):
    proj = _voiced(make_gallery(tmp_path / fmt, fmt), platform=plat)
    assert [i for i in safezone.scan(proj, chapter="ch01")] == []  # lab свёрстан в зоне площадки, вкл. Reels (35 % снизу)


# --- телефонные шаблоны (B2.1) -----------------------------------------------------------------------------------

@pytest.mark.parametrize("fmt,plat", [("vertical", "tiktok"), ("vertical", "youtube-shorts"),
                                      ("vertical", "instagram-reels"), ("portrait", "instagram-feed"),
                                      ("square", None)])
def test_phone_follows_platform_zone(tmp_path, fmt, plat):
    proj = _voiced(make_gallery(tmp_path / fmt, fmt), **({"platform": plat} if plat else {}))
    assert safezone.scan(proj, chapter="ch02") == []  # lock, feed, cards, questions, close — в зоне площадки
    tl, ctx = render.prepare(proj)
    s = next(s for s in tl["scenes"] if s["template"] == "phone_feed")
    tpl = render.make_template(ctx, s)
    tpl.setup()
    ph, a = tpl.phone, tpl.area
    half_h, half_w = ph.sh * ph.GLOW_H / 2, ph.sh * ph.GLOW_W / 2
    assert a.y0 <= ph.strip_cy < ph.cy - half_h and ph.cy + half_h <= a.y1 + 1  # полоса над телефоном, корпус в рамке
    assert a.x0 <= ph.cx - half_w and ph.cx + half_w <= a.x1
