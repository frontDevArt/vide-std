"""ROADMAP A2: бренд-кит `brand/brand.yaml` → стиль ролика. `lab` из кита Notes From The Mind рисует пиксель в
пиксель как встроенный пресет; тот же сценарий в ките другой студии — явно другой кадр."""
import pickle
import shutil

import numpy as np
import pytest
import yaml
from PIL import Image

from conftest import ROOT, make_gallery
from studio import brand, gfx, project, render, subs, timing, validate
from studio.selftest import golden_frames
from studio.style import STYLES, Style

NFTM_KIT = ROOT / "studios" / "notes-from-the-mind" / "brand"
SUNRISE = ROOT / "tests" / "fixtures" / "brands" / "sunrise"


def _kit(tmp_path, **raw):
    d = tmp_path / "kit"
    d.mkdir(exist_ok=True)
    (d / "brand.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return d


def _style(kit_dir, **st):
    return Style.from_cfg(dict(st, kit=brand.load(kit_dir)))


def _gallery(path, style):
    root = make_gallery(path)
    p = root / "project.yaml"
    y = yaml.safe_load(p.read_text(encoding="utf-8"))
    y["style"] = style
    p.write_text(yaml.safe_dump(y, allow_unicode=True), encoding="utf-8")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


# ------------------------------------------------------------------ кит Notes From The Mind ≡ пресет lab
@pytest.mark.parametrize("mood", [None, "ember"])
def test_nftm_kit_is_lab(mood):
    kit, lab = _style(NFTM_KIT, mood=mood), Style("lab", mood)
    assert dict(kit.pal) == dict(lab.pal)
    assert (kit.background, kit.camera, kit.subs) == (lab.background, lab.camera, lab.subs)
    import os
    assert kit.fonts == {r: os.path.normpath(os.path.join(gfx.ASSETS, p)) for r, p in STYLES["lab"]["fonts"].items()}
    assert kit != lab and kit.brand["name"] == "Notes From The Mind"


def test_nftm_kit_frames_pixel_identical(tmp_path):
    """Тот же сценарий (фикстура gallery, все шаблоны) — кит NFTM против palette: lab: кадры байт в байт."""
    a = golden_frames(_gallery(tmp_path / "lab", {"palette": "lab"}))
    b = golden_frames(_gallery(tmp_path / "kit", {"brand": str(NFTM_KIT)}))
    assert a.keys() == b.keys()
    for k in a:
        assert np.array_equal(np.asarray(a[k]), np.asarray(b[k])), k


def test_fake_discounts_uses_studio_kit():
    proj = project.load(ROOT / "studios" / "notes-from-the-mind" / "projects" / "fake-discounts")
    st = proj.cfg["style"]
    assert st["brand"] == "brand" and st["palette"] == "lab" and st["kit"]["name"] == "Notes From The Mind"
    assert "kit" in st and not any(p.startswith(("C:", "/")) for p in st["kit"]["fonts"].values())  # переносимо
    assert dict(Style.from_cfg(st).pal) == dict(Style("lab", "ember").pal)


# ------------------------------------------------------------------ другой кит — другой кадр
def test_other_kit_frames_differ(tmp_path):
    lab = golden_frames(_gallery(tmp_path / "lab", {"brand": str(NFTM_KIT)}))
    sun = golden_frames(_gallery(tmp_path / "sun", {"brand": str(SUNRISE)}))
    diffs = [np.abs(np.asarray(lab[k], np.int16) - np.asarray(sun[k], np.int16)).mean() for k in lab]
    assert min(diffs) > 8 and np.median(diffs) > 15, (min(diffs), np.median(diffs))
    s = Style.from_cfg({"kit": brand.load(SUNRISE)})
    assert (s.background, s.camera, s.subs) == ("gradient", False, "tiktok")
    assert s.pal["bg_top"] == (0x2A, 0x12, 0x20) and s.pal["bg_bot"] == (0x4A, 0x1C, 0x1C)  # ключ главнее роли
    assert s.pal["cyan"] == s.pal["accent"] == (0xFF, 0x8A, 0x3D) and s.pal["myth"] == (0xFF, 0x59, 0x64)
    assert s.shape == {"radius": 28, "line": 3}


def test_tiktok_subs(tmp_path):
    proj = _gallery(tmp_path / "sun", {"brand": str(SUNRISE)})
    base = int(round(min(proj.size) * 0.052))
    assert subs.font_size(proj) == int(base * subs.TIKTOK_SCALE)  # перенос и QA — крупным размером
    tl, ctx = render.prepare(proj)
    s = next(s for s in tl["scenes"] if s["subs"])
    c = s["subs"][0]
    W, H = ctx["W"], ctx["H"]
    t = (c["t0"] + c["t1"]) / 2
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    render.draw_subs(img, s, t, subs.font_size(proj), W, H, ctx["style"])
    a = np.asarray(img.convert("RGB"))
    accent = np.array(ctx["style"].pal["accent"])
    assert (np.abs(a - accent).sum(-1) < 30).sum() > 50  # звучащее слово — акцентом
    ys = np.nonzero(a.sum(-1).max(1))[0]
    assert H * 0.6 < ys.mean() < H * 0.95


# ------------------------------------------------------------------ фоны
def test_solid_and_image_backgrounds(tmp_path):
    Image.new("RGB", (40, 20), (200, 0, 0)).save(tmp_path / "photo.png")
    solid = _style(_kit(tmp_path, palette={"bg": "#102030"}, background="solid"))
    img = render._bg(64, 36, solid).frame(0.0)
    assert img.getpixel((5, 5)) == (16, 32, 48, 255) and img.getpixel((60, 30)) == (16, 32, 48, 255)
    photo = _style(_kit(tmp_path, palette={"bg": "#000000"},
                        background={"type": "image", "file": "../photo.png", "dim": 0.5}))
    img = render._bg(64, 36, photo).frame(0.0)
    assert img.size == (64, 36) and img.getpixel((32, 18))[:3] == (100, 0, 0)  # cover + затемнение к bg


# ------------------------------------------------------------------ проверка кита
@pytest.mark.parametrize("raw, msg", [
    ({"colour": 1}, "неизвестный ключ colour"),
    ({"base": "pastel"}, "base"),
    ({"palette": {"accent": "#12"}}, "palette.accent"),
    ({"palette": {"glow": "#123456"}}, "palette.glow"),
    ({"fonts": {"head": {"file": "Manrope-VF.ttf"}}}, "license"),
    ({"fonts": {"title": {"file": "Manrope-VF.ttf", "license": "OFL"}}}, "fonts.title"),
    ({"fonts": {"head": {"file": "Nope.ttf", "license": "OFL"}}}, "Nope.ttf"),
    ({"background": "video"}, "background"),
    ({"background": {"type": "image"}}, "background.file"),
    ({"subs": "huge"}, "subs"),
    ({"camera": "yes"}, "camera"),
    ({"logo": {"light": "logo.svg"}}, "logo.svg"),
    ({"shape": {"radius": -1}}, "shape.radius"),
])
def test_kit_errors(tmp_path, raw, msg):
    with pytest.raises(SystemExit, match=msg):
        brand.load(_kit(tmp_path, **raw))


def test_kit_assets_and_fonts_lookup(tmp_path):
    d = _kit(tmp_path, logo={"light": "logo.png"}, music="theme.wav",
             fonts={"head": {"file": "Own.ttf", "license": "client"}})
    (d / "fonts").mkdir()
    shutil.copy(ROOT / "assets" / "fonts" / "Manrope-VF.ttf", d / "fonts" / "Own.ttf")
    (d / "logo.png").write_bytes(b"x")
    (d / "theme.wav").write_bytes(b"x")
    kit = brand.load(d)
    assert kit["fonts"]["head"].endswith("kit/fonts/Own.ttf") and kit["logo"]["light"].endswith("kit/logo.png")
    assert gfx.font(40, style=Style.from_cfg({"kit": kit})).path.endswith("Own.ttf")


# ------------------------------------------------------------------ цепочка настроек и кэш
@pytest.fixture
def acme(tmp_path, monkeypatch):
    from studio import workspace
    shutil.copytree(ROOT / "projects" / "_template", tmp_path / "projects" / "_template")
    root = tmp_path / "studios" / "acme"
    (root / "projects").mkdir(parents=True)
    shutil.copytree(SUNRISE, root / "brand")
    (root / "brand" / "theme.wav").write_bytes(b"x")
    y = yaml.safe_load((root / "brand" / "brand.yaml").read_text(encoding="utf-8"))
    (root / "brand" / "brand.yaml").write_text(yaml.safe_dump(dict(y, music="theme.wav")), encoding="utf-8")
    (root / "studio.yaml").write_text(yaml.safe_dump({
        "kind": "brand", "defaults": {"language": "en", "tts": {"backend": "fake"}, "style": {"brand": "brand"}}}),
        encoding="utf-8")
    monkeypatch.setattr(workspace, "ROOT", tmp_path)
    with workspace.use(tmp_path):
        yield root


def _proj(root, slug, **cfg):
    p = root / "projects" / slug
    p.mkdir()
    (p / "project.yaml").write_text(yaml.safe_dump(dict({"title": "x", "topic": "x"}, **cfg)), encoding="utf-8")
    return project.load(p).cfg


def test_studio_default_brand(acme):
    cfg = _proj(acme, "promo")
    assert cfg["style"]["kit"]["name"] == "Sunrise Coffee" and cfg["style"]["palette"] == "lab"
    assert cfg["music"]["file"].endswith("theme.wav")  # музыка бренда по умолчанию
    assert _proj(acme, "own", music={"file": "mine.wav"})["music"]["file"] == "mine.wav"
    off = _proj(acme, "plain", style={"brand": None, "palette": "neon"})
    assert "kit" not in off["style"] and Style.from_cfg(off["style"]).palette == "neon"


def test_kit_edit_changes_render_key(acme):
    """Правка brand.yaml меняет ключ кэша рендера (стиль — в хэше cfg["style"]), путь кита — нет."""
    a = Style.from_cfg(_proj(acme, "a")["style"])
    f = acme / "brand" / "brand.yaml"
    f.write_text(f.read_text(encoding="utf-8").replace("#FF8A3D", "#00FF00"), encoding="utf-8")
    b = Style.from_cfg(_proj(acme, "b")["style"])
    assert a != b and a.key != b.key and b.pal["accent"] == (0, 255, 0)


def test_style_pickles_with_kit():
    s = _style(SUNRISE, mood="night")
    t = pickle.loads(pickle.dumps(s))
    assert t == s and hash(t) == hash(s) and dict(t.pal) == dict(s.pal) and t.subs == "tiktok"


def test_validate_mood_on_kit_is_clean(tmp_path):
    proj = project.load(make_gallery(tmp_path / "g"))
    proj.cfg["style"] = {"brand": str(NFTM_KIT), "mood": "ember", "kit": brand.load(NFTM_KIT), "palette": "lab"}
    errs, warns = [], []
    validate.style(proj, errs, warns)
    assert not errs and not warns
