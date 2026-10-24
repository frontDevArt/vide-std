"""ROADMAP C5.5: сцена с `image:` сама разворачивается в params шаблона media.image (imagegen.scene_params) —
параллакс по раскладке со слоями на месте `box`, стикер вырезанного объекта (целиком, тень по альфе), «до → после»;
слои — по битам, только по готовым PNG (fake), детерминированно. Прежний параллакс без `box` не меняется."""
import numpy as np
import pytest
import yaml
from PIL import Image
from test_images_command import SCENE, SUBJECT
from test_images_schema import _proj

from studio import cli, imagegen, project, render, timing, validate


def _quiet(*_a, **_k):
    pass


def _root(tmp_path, image, cutout="rembg", template=None):
    root = _proj(tmp_path, images={"enabled": True, "style": "flat vector", "backend": "fake", "cutout": cutout},
                 image=image)
    p = root / "script" / "ch01.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    s = next(s for s in d["scenes"] if s["id"] == "s02")
    s.pop("params")
    if template:
        s["template"] = template
    else:
        s.pop("template")  # сцена с image: без template — media.image
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return root


def _laid(root, images=True):
    if images:
        assert cli.main(["images", str(root)]) == 0
    proj = project.load(root)
    timing.layout(proj, log=_quiet)
    return proj


def _scene(proj):
    tl, ctx = render.prepare(proj)
    return next(s for s in tl["scenes"] if s["id"] == "s02"), ctx


def test_scene_without_template_is_image(tmp_path):
    proj = project.load(_root(tmp_path, SCENE))
    assert validate.check(proj).ok
    assert imagegen.template_of(proj.chapters[0][1]["scenes"][1]) == "media.image"
    assert imagegen.template_of({"id": "x"}) == "statement"


def test_layers_expand_to_parallax_with_boxes(tmp_path):
    proj = _laid(_root(tmp_path, SCENE))
    s, _ = _scene(proj)
    p = s["params"]
    meta = yaml.safe_load((imagegen.layers_dir(proj, imagegen.keys(proj)[0][2]) / "layers.json").read_text("utf-8"))
    assert p["motion"] == "parallax" and len(p["layers"]) == 3
    base, *fg = p["layers"]
    assert base["file"].endswith(".layers/base.png") and "box" not in base and base["depth"] == imagegen.BASE_DEPTH
    assert [L["box"] for L in fg] == [x["box"] for x in meta["layers"]]  # место — прямо из раскладки
    assert fg[0]["depth"] < fg[1]["depth"] == 1.0
    assert [L["at"] for L in fg] == [0, 1]  # ближние слои — по битам сцены


def test_subject_is_sticker_and_bg_subject_parallax(tmp_path):
    proj = _laid(_root(tmp_path, SUBJECT))
    L, = _scene(proj)[0]["params"]["layers"]
    assert L["sticker"] and L["file"].endswith(".cut.png") and L["box"] == imagegen.SUBJECT_BOX[proj.cfg["format"]]
    proj = _laid(_root(tmp_path / "b", [{"prompt": "an empty room", "role": "bg"}, SUBJECT], cutout="none"))
    bg, obj = _scene(proj)[0]["params"]["layers"]
    assert bg["depth"] == imagegen.BG_DEPTH and not obj["file"].endswith(".cut.png") and obj["sticker"]


def test_state_b_is_before_after_on_second_beat(tmp_path):
    proj = _laid(_root(tmp_path, [{"prompt": "a dark room", "role": "bg"}, {"prompt": "same, lit", "role": "state_b"}]))
    p = _scene(proj)[0]["params"]
    k = [k for _, _, k in imagegen.keys(proj)]
    assert p["motion"] == "before_after" and p["file"].endswith(f"{k[0]}.png") and p["after"].endswith(f"{k[1]}.png")
    assert p["at"] == 1


def test_explicit_params_win_and_other_templates_untouched(tmp_path):
    root = _root(tmp_path, SCENE)
    p = root / "script" / "ch01.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["scenes"][1]["params"] = {"motion": "kenburns", "caption": "Sleep"}
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    p_ = _scene(_laid(root))[0]["params"]
    assert p_["motion"] == "kenburns" and p_["caption"] == "Sleep" and p_["file"].startswith(imagegen.DIR)
    q = _scene(_laid(_root(tmp_path / "t", SCENE, template="statement")))[0]["params"]
    assert "layers" not in q and "file" not in q  # image: у чужого шаблона — его params


def test_missing_png_stops_render(tmp_path):
    proj = _laid(_root(tmp_path, SCENE), images=False)
    with pytest.raises(SystemExit, match="python -m studio images"):
        render.prepare(proj)


def _frame(proj, t):
    s, ctx = _scene(proj)
    tpl = render.make_template(ctx, s)
    img = Image.new("RGBA", (ctx["W"], ctx["H"]), (0, 0, 0, 255))
    tpl.draw(img, t, s["start"] + t)
    return s, tpl, np.asarray(img).astype(int)


def test_layers_appear_on_beats_deterministic(tmp_path):
    proj = _laid(_root(tmp_path, SCENE))
    s, tpl, _ = _frame(proj, 0.0)
    t1 = tpl.layers[2]["at"]
    assert tpl.layers[1]["at"] < t1 < s["dur"]
    before, after = _frame(proj, max(0.0, t1 - 0.05))[2], _frame(proj, t1 + 0.6)[2]
    assert np.abs(after - before).max() > 40  # ближний слой появился на своём бите
    assert np.array_equal(_frame(proj, 1.0)[2], _frame(proj, 1.0)[2])
    k1 = _scene(proj)[0]["key"]
    assert k1 == _scene(project.load(proj.root))[0]["key"]


def test_sticker_whole_with_alpha_shadow(tmp_path):
    proj = _laid(_root(tmp_path, SUBJECT))
    s, tpl, _ = _frame(proj, 0.0)
    L = tpl.layers[0]["img"]
    a = np.asarray(L.getchannel("A")).astype(int)
    rgb = np.asarray(L.convert("RGB")).astype(int)
    ys, xs = np.nonzero(a > 0)
    assert 0 < xs.min() and xs.max() < L.width - 1 and 0 < ys.min() and ys.max() < L.height - 1  # не обрезан
    cut = Image.open(imagegen.cut_path(proj, imagegen.keys(proj)[0][2]))
    obj = np.nonzero(a == 255)[0]
    assert obj.max() - obj.min() < cut.height * 1.2 * (1 + tpl.layers[0]["m"]) + 2  # не растянут больше MAX_UP
    shadow = (a > 0) & (rgb.sum(axis=2) < 10)  # тень — тёмная полупрозрачная кайма по альфе объекта
    assert shadow.any() and a[shadow].max() < 255


def test_box_layer_moves_less_than_legacy(tmp_path):
    proj = _laid(_root(tmp_path, SCENE))
    tpl = _frame(proj, 0.0)[1]
    near = tpl.layers[2]
    assert near["m"] == pytest.approx(0.03 + 0.05 * near["d"])  # было бы 0,05 + 0,10·d
    assert tpl.layers[0]["m"] == pytest.approx(0.05 + 0.10 * tpl.layers[0]["d"])  # слой без box — как раньше
