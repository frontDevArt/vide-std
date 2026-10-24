"""ROADMAP C5.2: схема картинок — блок `images:` (project.yaml и studio.yaml → defaults), запросы `image:` сцен,
проверки validate и фаза «3б Картинки» в status. Сети и денег нет: только схема и путь в кэше."""
import shutil
from pathlib import Path

import yaml

from studio import config, imagegen, project, status, validate, workspace

DEMO = Path(__file__).parent / "fixtures" / "kinds" / "explainer"
PROMPT = "a cozy bedroom at night, a person asleep in bed"


def _proj(tmp_path, images=None, image=None, scene="s02"):
    root = tmp_path / "p"
    shutil.copytree(DEMO, root)
    if images is not None:
        p = root / "project.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        data["images"] = images
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    if image is not None:
        p = root / "script" / "ch01.yaml"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        next(s for s in data["scenes"] if s["id"] == scene)["image"] = image
        p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return root


def _rep(root):
    return validate.check(project.load(root))


def test_no_block_cfg_unchanged(tmp_path):
    cfg = project.load(_proj(tmp_path)).cfg
    assert "images" not in cfg  # ключи кэша старых проектов прежние
    assert "images" not in config.DEFAULTS
    assert imagegen.enabled(cfg) is False
    assert "3б Картинки" not in [n for n, _, _ in status.phases(project.load(_proj(tmp_path / "x")))]


def test_block_gets_defaults_from_images_md(tmp_path):
    cfg = project.load(_proj(tmp_path, images={"enabled": True, "style": "flat vector"})).cfg
    im = cfg["images"]
    assert im["enabled"] is True and im["style"] == "flat vector"
    assert (im["backend"], im["model"], im["resolution"], im["cutout"], im["budget_usd"]) == \
        ("kie", "nano-banana-2", "2K", "rembg", 3)
    assert im["layers"] == "seedream/5-flash-layer-decomposition"
    assert not config.check({"images": {"enabled": True, "model": "x", "budget_usd": 1.5}})
    assert any("images.modle" in w for w in config.check({"images": {"modle": "x"}}))


def test_studio_defaults_enable_images(tmp_path, monkeypatch):
    sd = tmp_path / "studios" / "acme"
    (sd / "projects").mkdir(parents=True)
    (sd / "studio.yaml").write_text(yaml.safe_dump({"name": "acme", "kind": "brand", "languages": ["en"],
                                                    "defaults": {"images": {"enabled": True, "budget_usd": 5}}}),
                                    encoding="utf-8")
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    root = sd / "projects" / "p"
    shutil.copytree(DEMO, root)
    with workspace.use(tmp_path):
        im = project.load(root).cfg["images"]
    assert im["enabled"] is True and im["budget_usd"] == 5 and im["model"] == "nano-banana-2"


def test_image_when_disabled_is_error_with_hint(tmp_path):
    for images in (None, {"enabled": False}):
        rep = _rep(_proj(tmp_path / str(images is None), images=images, image={"prompt": PROMPT}))
        assert any("ch01/s02" in e and "images: {enabled: true}" in e for e in rep.errs), rep.errs


def test_image_when_enabled_ok(tmp_path):
    root = _proj(tmp_path, images={"enabled": True}, image=[
        {"prompt": PROMPT, "role": "scene", "layers": ["room", "bed with a person"]},
        {"prompt": "the same room, morning light", "role": "state_b", "variant": 2}])
    rep = _rep(root)
    assert not [e for e in rep.errs if "image" in e], rep.errs
    assert not [w for w in rep.warns if "image" in w], rep.warns


def test_bad_requests(tmp_path):
    rep = _rep(_proj(tmp_path, images={"enabled": True, "backend": "kei", "budget_usd": 0}, image=[
        {"prompt": " ", "role": "hero", "variant": -1, "seed": 1},
        "just a string"]))
    e, w = " | ".join(rep.errs), " | ".join(rep.warns)
    assert "images.backend: 'kei'" in e and "images.budget_usd" in e
    assert "нет prompt" in e and "role 'hero'" in e and "variant = -1" in e and "нужен словарь" in e
    assert "seed" in w


def test_state_b_needs_base_and_layers_only_for_scene(tmp_path):
    rep = _rep(_proj(tmp_path, images={"enabled": True},
                     image={"prompt": PROMPT, "role": "state_b", "layers": ["a"]}))
    assert any("state_b" in e for e in rep.errs)
    assert any("layers — только у role scene" in w for w in rep.warns)


def test_cache_key_and_status_phase(tmp_path):
    root = _proj(tmp_path, images={"enabled": True, "style": "flat"}, image=[
        {"prompt": PROMPT}, {"prompt": "same room, morning", "role": "state_b"}])
    proj = project.load(root)
    (w1, _, k1), (w2, _, k2) = imagegen.keys(proj)
    assert (w1, w2) == ("ch01/s02#0", "ch01/s02#1") and k1 != k2
    st = imagegen.settings(proj.cfg)
    assert k1 == imagegen.cache_key({"prompt": PROMPT}, st)
    for change in ({"style": "other"}, {"model": "google/nano-banana"}, {"resolution": "4K"}):
        assert imagegen.cache_key({"prompt": PROMPT}, {**st, **change}) != k1
    assert imagegen.cache_key({"prompt": PROMPT, "variant": 1}, st) != k1
    assert imagegen.cache_key({"prompt": PROMPT, "role": "bg"}, st) == k1  # роль — обработка, не картинка

    ph = {n: (ok, d) for n, ok, d in status.phases(proj)}
    assert ph["3б Картинки"][0] is False and "0/2" in ph["3б Картинки"][1]
    for _, _, k in imagegen.keys(proj):
        imagegen.path(proj, k).parent.mkdir(parents=True, exist_ok=True)
        imagegen.path(proj, k).write_bytes(b"png")
    ph = {n: (ok, d) for n, ok, d in status.phases(project.load(root))}
    assert ph["3б Картинки"] == (True, f"2/2 в {imagegen.DIR}/")
