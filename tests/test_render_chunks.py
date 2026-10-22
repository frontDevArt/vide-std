"""P3.3: длинная сцена рендерится кусками (каждый — свой mp4 с ключевым кадром), склейка `concat` без перекодирования.
Склеенная сцена = та же сцена одним куском: те же кадры, в том же порядке, без лишних и пропавших."""
import subprocess

import numpy as np
import pytest

from conftest import make_gallery
from studio import project, render, subs, timing


@pytest.mark.parametrize("n", [1, 59, 90, 120, 150, 179, 180, 240, 401, 1000])
def test_chunks_cover_scene(n):
    parts = render.chunks(n)
    assert parts[0][0] == 0 and parts[-1][1] == n
    assert all(a[1] == b[0] for a, b in zip(parts, parts[1:]))  # подряд, без дыр и наложений
    sizes = [f1 - f0 for f0, f1 in parts]
    assert max(sizes) - min(sizes) <= 1  # поровну: нет короткого «огрызка» в конце
    if n >= render.CHUNK:
        assert all(render.CHUNK * 2 / 3 <= x <= render.CHUNK * 1.5 for x in sizes), sizes


def test_short_scene_is_one_piece():
    assert render.chunks(90) == [(0, 90)]
    assert render.chunks(150) == [(0, 150)]  # 1,25 куска — не резать
    assert len(render.chunks(401)) == 3


def _decode(path, W, H):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                       capture_output=True, stdin=subprocess.DEVNULL, check=True)
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W, 3)


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    root = make_gallery(tmp_path_factory.mktemp("chunks") / "g", "vertical")
    proj = project.load(root)
    timing.layout(proj, log=lambda *_: None)
    tl, ctx = render.prepare(proj)
    s = next(s for s in tl["scenes"] if s["template"] == "lab_flow")  # камера + субтитры
    return proj, ctx, s


def test_joined_parts_equal_whole(scene, tmp_path):
    proj, ctx, s = scene
    W, H, n = ctx["W"], ctx["H"], s["n_frames"]
    size, args = subs.font_size(proj), (proj.cfg["render"]["crf"], proj.cfg["render"]["preset"])
    whole = tmp_path / "whole.mp4"
    render._render_scene_job(str(proj.root), s, ctx, size, whole, *args, 0, n, "k")
    bounds = render.chunks(n, n // 3)
    assert len(bounds) == 3
    parts = [tmp_path / f"p{i}.mp4" for i in range(len(bounds))]
    for p, (f0, f1) in zip(parts, bounds):
        render._render_scene_job(str(proj.root), s, ctx, size, p, *args, f0, f1, "k")
    joined = tmp_path / "joined.mp4"
    render.join_parts(parts, joined)
    a, b = _decode(whole, W, H), _decode(joined, W, H)
    assert len(a) == len(b) == n
    d = np.abs(a.astype(np.int16) - b.astype(np.int16))
    # куски кодируются отдельно — шум кодека на стыке; сдвиг на кадр дал бы средняя > 2 (selftest: MP4_MEAN)
    assert d.mean(axis=(1, 2, 3)).max() < 1.6
    for f0, _ in bounds:  # кадр стыка — ровно тот, что нарисован в процессе
        ref = np.asarray(render.frame(ctx, render.make_template(ctx, s), s, f0, size).convert("RGB"), np.int16)
        assert np.abs(b[f0].astype(np.int16) - ref).mean() < 1.6


def test_render_resumes_from_parts(scene, monkeypatch):
    """Прерванный рендер не начинает длинную сцену заново: готовые куски с верным ключом берутся из кэша."""
    proj, ctx, s = scene
    monkeypatch.setattr(render, "CHUNK", s["n_frames"] // 3)
    calls = []
    real = render._render_scene_job
    monkeypatch.setattr(render, "_render_scene_job", lambda *a: calls.append(a[7:9]) or real(*a))
    one = [x for x in render.prepare(proj)[0]["scenes"] if x["id"] == s["id"] and x["chapter"] == s["chapter"]]
    render.render_scenes(proj, one, ctx, workers=0, log=lambda *_: None)
    assert render.is_fresh(proj, one[0]) and len(calls) == 3
    assert not list(render.parts_dir(proj, s).glob(f"{s['id']}.*"))  # куски после склейки удалены
    # «прерванный» рендер: первый кусок уже готов, сцены ещё нет
    out = render.scene_out(proj, s)
    f0, f1 = render.chunks(s["n_frames"])[0]
    p = render.part_out(proj, s, f0, f1)
    render._render_scene_job(str(proj.root), s, ctx, subs.font_size(proj), p, proj.cfg["render"]["crf"],
                             proj.cfg["render"]["preset"], f0, f1, render.part_key(s, f0, f1))
    out.unlink()
    calls.clear()
    render.render_scenes(proj, one, ctx, workers=0, log=lambda *_: None)
    assert render.is_fresh(proj, one[0]) and sorted(calls) == render.chunks(s["n_frames"])[1:]
