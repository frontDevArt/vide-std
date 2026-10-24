"""P0.4: golden фикстуры gallery — timeline.json и .srt байт в байт, кадры PNG с допуском. ROADMAP C4: то же для
фикстуры library (шаблоны kit, commerce, media; кадры с TikTok-субтитрами) — tests/golden/library/<формат>/.

Golden меняется только флагом: pytest tests/test_golden.py --update-golden — и в коммите объясняется почему
(REFACTOR_PLAN, правило 3: на рефакторинге golden не меняется вообще).
Кадры хранятся в половинном разрешении (усреднение 2×2): в полном зерно фона даёт ~100 МБ PNG.
Кадры, допуски и пути — общие с `python -m studio selftest` (studio/selftest.py).
При расхождении кадров факт и карта разницы — в tests/.golden-diff/<формат>/.
"""
import shutil

import pytest

from conftest import ROOT, make_gallery
from studio import project, timing
from studio.selftest import (DIFF, GOLDEN, LIB_GOLDEN, MAX_DIFF, MEAN_DIFF, compare_frames, frame_diff as _diff,
                             golden_frames as _frames, loose_frames, make_library, subs_frames)


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


def test_frames(voiced, update):
    fmt = voiced.cfg["format"]
    _check_frames(_frames(voiced), GOLDEN / fmt / "frames", DIFF / fmt, update, fmt)


def _check_frames(frames, gdir, ddir, update, what, loose=()):
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
            pytest.skip(f"golden {what}/frames обновлён: {len(changed)} кадров, удалено {len(stale)}")
        return
    bad, _ = compare_frames(frames, gdir, ddir, loose=loose)
    assert not bad, (
        f"кадры {what} разошлись с golden (допуск: макс ≤ {MAX_DIFF}, средняя ≤ {MEAN_DIFF}); "
        f"факт и карта разницы — {ddir.relative_to(ROOT)}\n  " + "\n  ".join(bad))


# ------------------------------------------------------------------ library (ROADMAP C4)
@pytest.fixture(scope="module", params=["horizontal", "vertical"])
def library(request, tmp_path_factory):
    work = tmp_path_factory.mktemp("lib-" + request.param)
    proj = project.load(make_library(work / "library", request.param))
    tl = timing.layout(proj, log=lambda *_: None)
    return proj, tl, work


def test_library_timeline(library, update):
    proj, _, _ = library
    _check_bytes(LIB_GOLDEN / proj.cfg["format"] / "timeline.json", (proj.build / "timeline.json").read_bytes(), update)


def test_library_frames(library, update):
    """Каждый шаблон kit/commerce/media — по 2 кадра на сцену, плюс TikTok-субтитры (subtitles.style)."""
    proj, tl, work = library
    fmt = proj.cfg["format"]
    frames = _frames(proj)
    frames.update(subs_frames(work, fmt))
    _check_frames(frames, LIB_GOLDEN / fmt / "frames", DIFF / "library" / fmt, update, f"library/{fmt}",
                  loose_frames(tl))
