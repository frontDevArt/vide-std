"""P4.2: промежуточные WAV микса — во временной папке; в build/mix/ остаются петля музыки и levels.json для qa."""
import json

from conftest import make_gallery
from studio import assemble, project, qa, render, timing


def test_mix_wavs_not_kept(tmp_path):
    quiet = lambda *_a, **_k: None  # noqa: E731
    proj = project.load(make_gallery(tmp_path / "gallery", "horizontal"))
    timing.layout(proj, log=quiet)
    render.render(proj, workers=2, log=quiet)
    md = proj.bdir("mix")
    (md / "voice.wav").write_bytes(b"old")  # остаток сборки до P4.2 — новая сборка его убирает
    assemble.assemble(proj, log=quiet)
    assert sorted(p.name for p in md.glob("*.wav")) == ["music_loop.wav"]  # петля — кэш, не промежуточный файл
    lv = json.loads((md / "levels.json").read_text(encoding="utf-8"))
    assert lv["voice_lufs"] is not None and lv["music_lufs"] is not None
    qa.run(proj, log=quiet, fast=True)
    rep = (proj.qa_dir / "report.md").read_text(encoding="utf-8")
    assert "Музыка значительно тише речи, но слышна" in rep
