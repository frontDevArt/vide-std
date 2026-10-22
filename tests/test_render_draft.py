"""P3.4: черновой рендер `render --draft` — половина разрешения, x264 `ultrafast`, свой кэш build/render-draft/.
Черновой кадр = чистовой, уменьшенный вдвое (шаблоны рисуют в долях W/H); чистовой кэш и финал не трогаются."""
import json
import subprocess

import numpy as np
import pytest
from PIL import Image

from conftest import make_gallery
from studio import assemble, project, render, timing


@pytest.fixture(scope="module", params=["vertical", "horizontal", "square"])
def voiced(request, tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("draft") / "gallery", request.param)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


def test_draft_ctx_half_size(voiced):
    tl, ctx = render.prepare(voiced)
    tld, dctx = render.prepare(voiced, draft=True)
    W, H = tl["size"]
    assert (dctx["W"], dctx["H"]) == (W // 2, H // 2) and dctx["W"] % 2 == dctx["H"] % 2 == 0  # yuv420p
    assert dctx["preset"] == render.DRAFT_PRESET and ctx["preset"] == voiced.cfg["render"]["preset"]
    assert render.sub_size(voiced, dctx) == render.sub_size(voiced, ctx) // 2
    for s, d in zip(tl["scenes"], tld["scenes"]):
        assert s["key"] != d["key"]  # черновик не выдаёт себя за чистовую сцену
        assert render.scene_out(voiced, s).parent.parent.name == "render"
        assert render.scene_out(voiced, d).parent.parent.name == "render-draft"


def test_draft_frame_is_downscaled_full(voiced):
    """Каждый шаблон на полразмера рисует ту же картинку: сравнение с чистовым кадром, уменьшенным BOX."""
    tl, ctx = render.prepare(voiced)
    tld, dctx = render.prepare(voiced, draft=True)
    means = []
    for s, d in zip(tl["scenes"], tld["scenes"]):
        f = s["n_frames"] * 2 // 3
        a = render.frame(ctx, render.make_template(ctx, s), s, f, render.sub_size(voiced, ctx))
        b = render.frame(dctx, render.make_template(dctx, d), d, f, render.sub_size(voiced, dctx))
        a = a.convert("RGB").resize((dctx["W"], dctx["H"]), Image.BOX)
        diff = float(np.abs(np.asarray(a, np.int16) - np.asarray(b.convert("RGB"), np.int16)).mean())
        # phone_*: лента сдвинута округлениями на несколько px, рамка в px не масштабируется (ярче ореол)
        assert diff < 12, (s["chapter"], s["id"], s["template"], diff)
        means.append(diff)
    assert np.mean(means) < 3.5, means


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,nb_frames", "-of", "json", str(path)],
                       capture_output=True, stdin=subprocess.DEVNULL, check=True)
    return json.loads(r.stdout)["streams"][0]


def test_draft_render_and_assemble(tmp_path):
    root = make_gallery(tmp_path / "gallery", "vertical")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    render.render(proj, log=lambda *_: None, draft=True)
    assert not (proj.build / "render").exists()  # чистовой кэш не тронут
    tl, _ = render.prepare(proj)
    tld, _ = render.prepare(proj, draft=True)
    assert all(render.is_fresh(proj, s) for s in tld["scenes"])
    assert not any(render.is_fresh(proj, s) for s in tl["scenes"])
    s = tld["scenes"][0]
    st = _probe(render.scene_out(proj, s))
    assert (st["width"], st["height"]) == (540, 960) and int(st["nb_frames"]) == s["n_frames"]
    logs = []
    render.render(proj, log=logs.append, draft=True)
    assert logs == ["Все сцены актуальны — рендерить нечего."]  # свой кэш работает
    with pytest.raises(SystemExit, match="render <проект>$"):  # чистовой кэш пуст — чистовая сборка не идёт
        assemble.assemble(proj, log=lambda *_: None)
    final = assemble.assemble(proj, log=lambda *_: None, draft=True)
    assert final.endswith("gallery.draft.mp4") and not proj.final_path().exists()
    st = _probe(final)
    assert (st["width"], st["height"]) == (540, 960) and int(st["nb_frames"]) == tld["total_frames"]

