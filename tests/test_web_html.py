"""Шаблон web.html — второй движок, HTML/CSS в headless Chromium (ROADMAP C6).

Ключ кэша от содержимого страницы проверяется всегда; кадры, черновик и склейка — только при playwright с Chromium
(не входят в requirements, в CI их нет). Замеры — tools/bench_html.py.
"""
import json
import shutil
import subprocess

import numpy as np
import pytest

from studio import assemble, project, render, timing
from studio.project import STUDIO_ROOT as ROOT

FIXTURE = ROOT / "tests" / "fixtures" / "web"


@pytest.fixture(scope="module")
def proj(tmp_path_factory):
    d = tmp_path_factory.mktemp("web") / "web"
    shutil.copytree(FIXTURE, d)
    timing.layout(project.load(d), log=lambda *_: None)
    return project.load(d)


@pytest.fixture(scope="module")
def browser():
    pytest.importorskip("playwright")
    from studio.packs.web import browser as B
    if not B.available():
        pytest.skip("нет Chromium для playwright")
    yield B
    B.close()


def _scene(proj, sid, draft=False):
    tl, ctx = render.prepare(proj, draft)
    s = next(s for s in tl["scenes"] if s["id"] == sid)
    return s, render.make_template(ctx, s)


def _pm(img):
    """Премультиплицированный RGBA: цвет пикселей с альфой 1–2 — шум растра, в кадр не попадает."""
    a = np.asarray(img).astype(np.int32)
    return np.concatenate([a[..., :3] * a[..., 3:] // 255, a[..., 3:]], -1)


def test_page_content_is_in_cache_key(proj):
    tl, _ = render.prepare(proj)
    key = {s["id"]: s["key"] for s in tl["scenes"]}
    page = proj.root / "assets" / "rich.html"
    page.write_text(page.read_text(encoding="utf-8").replace("Two engines", "Two  engines"), encoding="utf-8")
    try:
        tl2, _ = render.prepare(proj)
        key2 = {s["id"]: s["key"] for s in tl2["scenes"]}
        assert key2["s02"] != key["s02"] and key2["s01"] == key["s01"] and key2["s03"] == key["s03"]
    finally:
        shutil.copy(FIXTURE / "assets" / "rich.html", page)


def test_layer_follows_beats(proj, browser):
    s, tpl = _scene(proj, "s02")
    alpha = lambda t: np.asarray(tpl.layer(t))[..., 3].astype(int)  # noqa: E731
    assert alpha(0).max() == 0  # до первого бита и входа сцены — пусто: под страницей наш фон
    mid = alpha((s["beats"][1]["t0"] + s["beats"][2]["t0"]) / 2)
    assert (mid > 200).mean() > 0.1  # карточка на месте
    assert tpl.layer(1.0).size == (tpl.W, tpl.H)


def test_virtual_time_is_deterministic(proj, browser):
    s, tpl = _scene(proj, "s02")
    t = s["beats"][1]["t0"] + 0.4
    a = tpl.layer(t)
    tpl.layer(t + 1.5)
    assert np.array_equal(np.asarray(tpl.layer(t)), np.asarray(a))  # назад по времени — тот же кадр
    browser.close()  # первый кадр куска в другом процессе: свежий браузер
    assert np.abs(_pm(tpl.layer(t)) - _pm(a)).max() <= 2  # допуск golden (P0.4)


def test_draft_is_same_layout(proj, browser):
    s, full = _scene(proj, "s02")
    _, draft = _scene(proj, "s02", draft=True)
    t = s["beats"][2]["t0"] + 0.5
    a = _pm(full.layer(t).reduce(2)).astype(float)
    b = _pm(draft.layer(t)).astype(float)
    assert b.shape == a.shape and np.abs(a - b).mean() < 3


def test_render_and_concat(proj, browser):
    render.render(proj, workers=0, draft=True, log=lambda *_: None)
    final = assemble.assemble(proj, log=lambda *_: None, draft=True)
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                        "stream=nb_read_frames", "-of", "json", str(final)],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    tl, _ = render.prepare(proj, draft=True)
    assert int(json.loads(r.stdout)["streams"][0]["nb_read_frames"]) == sum(s["n_frames"] for s in tl["scenes"])
