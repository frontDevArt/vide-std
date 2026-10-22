"""P0.4: golden фикстуры gallery — timeline.json и .srt байт в байт, кадры PNG с допуском.

Golden меняется только флагом: pytest tests/test_golden.py --update-golden — и в коммите объясняется почему
(REFACTOR_PLAN, правило 3: на рефакторинге golden не меняется вообще).
Кадры хранятся в половинном разрешении (усреднение 2×2): в полном зерно фона даёт ~100 МБ PNG.
При расхождении кадров факт и карта разницы — в tests/.golden-diff/<формат>/.
"""
import shutil

import numpy as np
import pytest
from PIL import Image

from conftest import ROOT, make_gallery
from studio import project, render, subs, timing

GOLDEN = ROOT / "tests" / "golden"
DIFF = ROOT / "tests" / ".golden-diff"
FRACS = (0.3, 0.85)  # кадры сцены: посреди входа и почти в конце, когда всё вышло
MAX_DIFF, MEAN_DIFF = 2, 0.1  # из 255: максимум по пикселю и среднее по кадру


@pytest.fixture
def update(request):
    return request.config.getoption("--update-golden")


@pytest.fixture(scope="module", params=["horizontal", "vertical"])
def voiced(request, tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp(request.param) / "gallery", request.param)
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    return proj


def _check_bytes(golden, actual: bytes, update):
    if golden.exists() and golden.read_bytes() == actual:
        return
    if update:
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(actual)
        pytest.skip(f"golden обновлён: {golden.relative_to(ROOT)}")
    assert golden.exists(), f"нет {golden.relative_to(ROOT)} — создать: pytest {__file__} --update-golden"
    exp, act = golden.read_text(encoding="utf-8").splitlines(), actual.decode("utf-8").splitlines()
    first = next((i for i, (a, b) in enumerate(zip(exp, act)) if a != b), min(len(exp), len(act)))
    pytest.fail(f"{golden.relative_to(ROOT)} отличается, строка {first + 1}:\n"
                f"  golden: {exp[first] if first < len(exp) else '<конец>'}\n"
                f"  сейчас: {act[first] if first < len(act) else '<конец>'}")


def test_timeline(voiced, update):
    actual = (voiced.build / "timeline.json").read_bytes()
    _check_bytes(GOLDEN / voiced.cfg["format"] / "timeline.json", actual, update)


def test_srt(voiced, update):
    actual = (voiced.bdir("final") / "gallery.srt").read_bytes()
    _check_bytes(GOLDEN / voiced.cfg["format"] / "gallery.srt", actual, update)


def _frames(proj):
    """{имя: кадр в половинном разрешении} — по FRACS на каждую сцену."""
    tl, ctx = render.prepare(proj)
    sub_size = subs.font_size(proj)
    out = {}
    for s in tl["scenes"]:
        tpl = render.make_template(ctx, s)
        for fr in FRACS:
            f = int(s["n_frames"] * fr)
            img = render.frame(ctx, tpl, s, f, sub_size).convert("RGB").reduce(2)
            out[f"{s['chapter']}-{s['id']}-f{f:04d}.png"] = img
    return out


def test_frames(voiced, update):
    fmt = voiced.cfg["format"]
    gdir, ddir = GOLDEN / fmt / "frames", DIFF / fmt
    frames = _frames(voiced)
    shutil.rmtree(ddir, ignore_errors=True)
    if update:
        gdir.mkdir(parents=True, exist_ok=True)
        stale = [p for p in gdir.glob("*.png") if p.name not in frames]
        for p in stale:
            p.unlink()
        changed = [n for n, img in frames.items() if not (gdir / n).exists() or _diff(gdir / n, img)[0]]
        for n in changed:
            frames[n].save(gdir / n, optimize=True)
        if changed or stale:
            pytest.skip(f"golden {fmt}/frames обновлён: {len(changed)} кадров, удалено {len(stale)}")
        return
    bad = []
    extra = sorted(p.name for p in gdir.glob("*.png") if p.name not in frames)
    for n, img in frames.items():
        g = gdir / n
        if not g.exists():
            bad.append(f"{n}: нет golden")
            continue
        fail, mx, mean, d = _diff(g, img)
        if fail:
            ddir.mkdir(parents=True, exist_ok=True)
            img.save(ddir / n)
            Image.fromarray(np.clip(d * 32, 0, 255).astype(np.uint8)).save(ddir / n.replace(".png", "_diff.png"))
            bad.append(f"{n}: макс {mx}, средняя {mean:.3f}")
    assert not bad and not extra, (
        f"кадры {fmt} разошлись с golden (допуск: макс ≤ {MAX_DIFF}, средняя ≤ {MEAN_DIFF}); "
        f"факт и карта разницы — {ddir.relative_to(ROOT)}\n  " + "\n  ".join(bad + [f"{n}: лишний golden" for n in extra]))


def _diff(golden, img):
    """(не в допуске, макс, средняя, |разница| по пикселям)."""
    g = np.asarray(Image.open(golden).convert("RGB"), dtype=np.int16)
    a = np.asarray(img, dtype=np.int16)
    if g.shape != a.shape:
        return True, 255, 255.0, np.full(a.shape, 255, np.int16)
    d = np.abs(a - g)
    mx, mean = int(d.max()), float(d.mean())
    return mx > MAX_DIFF or mean > MEAN_DIFF, mx, mean, d
