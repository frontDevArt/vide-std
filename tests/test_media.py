"""ROADMAP C2: медиа-слой — ассеты проекта (assets/ + assets.yaml), шаблоны media.* (image, video, screen, clip,
logo_sting, product_card), звук исходника в миксе, прозрачный экспорт. Демо — tests/fixtures/kinds/{promo, slideshow,
tutorial, clip}/ (полная цепочка до QA — `python -m studio selftest --kinds`)."""
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
import yaml
from PIL import Image

from studio import assets, audio, media, project, render, safezone, timing, validate
from studio.packs import REGISTRY

DEMOS = Path(__file__).parent / "fixtures" / "kinds"
MEDIA = {"media.image", "media.video", "media.screen", "media.clip", "media.logo_sting", "media.product_card"}


def _quiet(*_a, **_k):
    pass


def _demo(tmp_path, name, fmt=None, drop_deliverables=False):
    dst = tmp_path / name
    shutil.copytree(DEMOS / name, dst)
    if fmt or drop_deliverables:
        p = dst / "project.yaml"
        d = yaml.safe_load(p.read_text(encoding="utf-8"))
        if fmt:
            d["format"] = fmt
        d.pop("deliverables", None)
        p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return dst


def _laid(root):
    proj = project.load(root)
    timing.layout(proj, log=_quiet)
    return proj


# ------------------------------------------------------------------ ассеты
def test_refs_walks_params():
    p = {"file": "assets/a.jpg", "layers": [{"file": "assets/b.png"}, {"file": "assets/a.jpg"}],
         "caption": "a.jpg is a photo\nnot a file", "zoom": [1, 1.1], "source": "assets/c.MP4"}
    assert assets.refs(p) == ["assets/a.jpg", "assets/b.png", "assets/c.MP4"]
    assert assets.refs(None) == []


def test_validate_asset_issues(tmp_path):
    root = _demo(tmp_path, "promo")
    assert validate.check(project.load(root)).ok
    reg = root / "assets.yaml"
    d = yaml.safe_load(reg.read_text(encoding="utf-8"))
    d["assets"] = [e for e in d["assets"] if e["file"] != "assets/logo.png"]  # не записан
    d["assets"][0]["license"] = ""                                            # без лицензии
    d["assets"].append({"file": "assets/gone.jpg", "source": "x", "license": "y"})  # записан, файла нет
    reg.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    (root / "assets" / "lamp-night.jpg").unlink()                             # сцена ссылается, файла нет
    rep = validate.check(project.load(root))
    assert any("assets/lamp-night.jpg" in e and "нет файла" in e for e in rep.errs)
    assert any("assets.yaml: нет файла assets/gone.jpg" in e for e in rep.errs)
    assert any("assets/logo.png" in w and "assets.yaml" in w for w in rep.warns)
    assert any("lamp-front.jpg" in w and "license" in w for w in rep.warns)


def test_qa_check_needs_license(tmp_path):
    root = _demo(tmp_path, "promo")
    ok, det = assets.qa_check(project.load(root))
    assert ok and "4 файлов" in det and "CC0" in det
    (root / "assets.yaml").unlink()
    ok, det = assets.qa_check(project.load(root))
    assert not ok and "assets/logo.png" in det
    assert assets.qa_check(project.load(_demo(tmp_path, "explainer"))) is None  # без медиа — проверка неприменима


def test_asset_content_in_render_key(tmp_path):
    proj = _laid(_demo(tmp_path, "promo", drop_deliverables=True))
    tl, _ = render.prepare(proj)
    keys = {s["id"]: s["key"] for s in tl["scenes"]}
    img = Image.open(proj.root / "assets" / "lamp-front.jpg")
    img.transpose(Image.FLIP_LEFT_RIGHT).save(proj.root / "assets" / "lamp-front.jpg")  # то же имя, другое фото
    tl2, _ = render.prepare(project.load(proj.root))
    keys2 = {s["id"]: s["key"] for s in tl2["scenes"]}
    assert keys2["s02"] != keys["s02"]                       # сцена с этим фото перерисуется
    assert {k: v for k, v in keys2.items() if k != "s02"} == {k: v for k, v in keys.items() if k != "s02"}


# ------------------------------------------------------------------ шаблоны: рисуют, вёрстка в зоне
def test_media_pack_registered():
    assert MEDIA <= set(REGISTRY.templates())


@pytest.mark.parametrize("fmt", ["vertical", "horizontal", "square"])
@pytest.mark.parametrize("demo", ["promo", "slideshow", "tutorial", "clip"])
def test_demo_frames_in_every_format(tmp_path, demo, fmt):
    proj = _laid(_demo(tmp_path, demo, fmt=fmt))
    tl, ctx = render.prepare(proj)
    used = set()
    for s in tl["scenes"]:
        used.add(REGISTRY.canonical(s["template"]))
        mid = render.frame(ctx, render.make_template(ctx, s), s, s["n_frames"] * 2 // 3, 40, alpha=True)
        assert (np.asarray(mid)[:, :, 3] > 40).mean() > 0.003, f"{s['id']}: пустой кадр"  # что-то нарисовано
    assert safezone.scan(proj) == [], [safezone.message(i) for i in safezone.scan(proj)]
    if demo == "promo":
        assert {"media.logo_sting", "media.image", "media.product_card"} <= used


def test_full_frame_photo_is_backdrop(tmp_path):
    """Фото на весь кадр — подложка: под обрез можно, safezone проверяет подпись поверх, а не фото."""
    proj = _laid(_demo(tmp_path, "slideshow"))
    tl, ctx = render.prepare(proj)
    s = tl["scenes"][0]
    tpl = render.make_template(ctx, s)
    full = Image.new("RGBA", (ctx["W"], ctx["H"]), (0, 0, 0, 0))
    tpl.draw(full, s["dur"] / 2, 0)
    assert full.getbbox() == (0, 0, ctx["W"], ctx["H"])
    box = safezone.content_box(ctx, tpl, s, s["dur"] / 2)
    assert box and box[1] > ctx["H"] * 0.5  # только подпись внизу


def test_logo_from_brand_kit_or_text(tmp_path):
    proj = _laid(_demo(tmp_path, "promo", drop_deliverables=True))
    tl, ctx = render.prepare(proj)
    s = dict(tl["scenes"][0], params={"tagline": "Hi"})
    tpl = render.make_template(ctx, s)  # ни файла, ни кита — имя текстом (пустое имя не падает)
    render.frame(ctx, tpl, s, 20, 40)
    s = dict(tl["scenes"][0], params={"text": "AURORA"})
    img = render.frame(ctx, render.make_template(ctx, s), s, 20, 40, alpha=True)
    assert img.getbbox() is not None


# ------------------------------------------------------------------ видео и звук
def test_video_seek_matches_sequential():
    src = DEMOS / "tutorial" / "assets" / "screen.mp4"
    v = media.Video(src, 320, 180, 30, start=2.0)
    seq = [np.asarray(v.frame(k), np.int16) for k in range(12)]
    v.close()
    w = media.Video(src, 320, 180, 30, start=2.0)
    jump = np.asarray(w.frame(11), np.int16)             # сразу в кадр 11 (как кусок рендера с f0 = 11)
    back = np.asarray(w.frame(3), np.int16)              # назад — перезапуск
    end = w.frame(10_000)                                 # за концом исходника — последний кадр, без ошибки
    w.close()
    assert np.abs(jump - seq[11]).mean() < 1.0
    assert np.abs(back - seq[3]).mean() < 1.0
    assert end.size == (320, 180)


def test_clip_audio_goes_to_mix(tmp_path):
    proj = _laid(_demo(tmp_path, "clip"))
    tl = timing.load_timeline(proj)
    clips = audio.media_track(proj, tl)
    assert len(clips) == 1
    a, y = clips[0]
    assert a == 0 and abs(len(y) / audio.SR - tl["duration"]) < 0.05
    assert float(np.sqrt(np.mean(y ** 2))) > 0.01          # «речь» исходника звучит
    out = Path(audio.voice_track(proj, tl, tmp_path))
    v = media.audio(out)
    assert float(np.abs(v).max()) > 0.05


def test_video_without_audio_flag_is_silent(tmp_path):
    proj = _laid(_demo(tmp_path, "tutorial"))
    assert audio.media_track(proj, timing.load_timeline(proj)) == []  # screen: audio по умолчанию выключен


def test_export_alpha_mov(tmp_path):
    root = _demo(tmp_path, "tutorial")
    p = root / "script" / "ch01.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["scenes"] = d["scenes"][:1]  # одна сцена — быстро
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    proj = _laid(root)
    out = render.export_alpha(proj, "mov", log=_quiet)
    assert out.name == "tutorial.alpha.mov"
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                        "stream=codec_name,pix_fmt", "-of", "csv=p=0", str(out)], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL)
    assert r.stdout.strip().startswith("prores") and "yuva" in r.stdout
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", str(out), "-frames:v", "1", "-pix_fmt", "rgba",
                    str(png)], check=True, stdin=subprocess.DEVNULL)
    a = np.asarray(Image.open(png))[:, :, 3]
    assert a[5, 5] == 0 and a.max() == 255  # фон прозрачный, заголовок непрозрачный
