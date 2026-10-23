"""P4.1: финал склеивается прямо из сцен; build/chapters/ (копия render/) — только по флагу `--chapters`."""
import json
import subprocess

from conftest import make_gallery
from studio import assemble, project, render, timing


def _frames(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
                        "-show_entries", "stream=nb_read_packets", "-of", "json", str(path)],
                       capture_output=True, stdin=subprocess.DEVNULL, check=True)
    return int(json.loads(r.stdout)["streams"][0]["nb_read_packets"])


def test_final_from_scenes_chapters_on_flag(tmp_path):
    quiet = lambda *_a, **_k: None  # noqa: E731
    proj = project.load(make_gallery(tmp_path / "gallery", "horizontal"))
    timing.layout(proj, log=quiet)
    render.render(proj, workers=2, log=quiet)
    tl, _ = render.prepare(proj)
    final = assemble.assemble(proj, log=quiet)
    assert _frames(final) == tl["total_frames"]
    assert not (proj.build / "chapters").exists()  # копии render/ больше нет
    assemble.assemble(proj, log=quiet, chapters=True)
    chs = sorted({s["chapter"] for s in tl["scenes"]})
    got = sorted(p.stem for p in (proj.build / "chapters").glob("*.mp4"))
    assert got == chs
    assert sum(_frames(proj.build / "chapters" / f"{c}.mp4") for c in chs) == tl["total_frames"]
