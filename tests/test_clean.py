"""P4.3: `clean` — чистка кэшей build/ с отчётом; TTS из таймлайна и платный кэш не трогаются."""
import json
import os
import time

import pytest

from conftest import make_gallery
from studio import clean, cli, project


def _fill(root, backend="fake"):
    """Сборка без рендера: файлы на своих местах, таймлайн ссылается на одну строку TTS."""
    proj = project.load(root)
    proj.cfg["tts"]["backend"] = backend
    b = proj.build
    files = {
        "render/ch01/s01.mp4": 1000, "render/ch01/s01.mp4.key": 10, "render/ch01/parts/s02.00000-00050.mp4": 300,
        "render-draft/ch01/s01.mp4": 400, "chapters/ch01.mp4": 1000,
        "mix/music_loop.wav": 200, "mix/voice.wav": 500, "mix/levels.json": 20,
        "final/gallery.mp4": 2000, "final/gallery.srt": 5, "final/gallery.vtt": 5, "final/gallery.draft.mp4": 700,
        "tts/used.wav": 100, "tts/used.words.json": 3, "tts/old.wav": 90, "tts/old.words.json": 3,
        "render_ch01.log": 7, "voice_calibration.json": 4,
    }
    for rel, n in files.items():
        p = b / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x" * n)
    (b / "timeline.json").write_text(json.dumps({"scenes": [{"lines": [{"wav": "used.wav"}]}]}), encoding="utf-8")
    return proj


def _left(proj):
    return sorted(p.relative_to(proj.build).as_posix() for p in proj.build.rglob("*") if p.is_file())


def test_clean_all(tmp_path):
    proj = _fill(make_gallery(tmp_path / "g", "horizontal"))
    freed = clean.clean(proj, log=lambda *_: None)
    assert _left(proj) == ["timeline.json", "tts/used.wav", "tts/used.words.json", "voice_calibration.json"]
    assert freed == 1000 + 10 + 300 + 400 + 1000 + 200 + 500 + 20 + 2000 + 5 + 5 + 700 + 90 + 3 + 7


def test_keep_final(tmp_path):
    proj = _fill(make_gallery(tmp_path / "g", "horizontal"))
    clean.clean(proj, keep_final=True, log=lambda *_: None)
    left = _left(proj)
    # финал и levels.json (по нему qa проверяет громкость) остаются, черновик финала — нет
    assert {"final/gallery.mp4", "final/gallery.srt", "final/gallery.vtt", "mix/levels.json"} <= set(left)
    assert "final/gallery.draft.mp4" not in left and "mix/voice.wav" not in left and "render/ch01/s01.mp4" not in left


def test_paid_tts_kept(tmp_path):
    proj = _fill(make_gallery(tmp_path / "g", "horizontal"), backend="elevenlabs")
    clean.clean(proj, log=lambda *_: None)
    assert {"tts/old.wav", "tts/old.words.json"} <= set(_left(proj))  # платный синтез: кэш дороже места


def test_dry_run(tmp_path):
    proj = _fill(make_gallery(tmp_path / "g", "horizontal"))
    before = _left(proj)
    assert clean.clean(proj, dry_run=True, log=lambda *_: None) > 0
    assert _left(proj) == before


def test_age():
    assert clean.parse_age("30d") == 30 * 86400
    assert clean.parse_age("12h") == 12 * 3600
    assert clean.parse_age("2w") == 14 * 86400
    assert clean.parse_age("7") == 7 * 86400
    with pytest.raises(ValueError):
        clean.parse_age("soon")


def test_older_than_skips_fresh(tmp_path, capsys):
    root = make_gallery(tmp_path / "g", "horizontal")
    _fill(root)
    assert cli.main(["clean", str(root), "--older-than", "30d"]) == 0
    assert (root / "build" / "render" / "ch01" / "s01.mp4").exists()  # проект свежий — не тронут
    old = time.time() - 40 * 86400
    for p in root.rglob("*"):
        os.utime(p, (old, old))
    assert cli.main(["clean", str(root), "--older-than", "30d"]) == 0
    assert not (root / "build" / "render").exists()


def test_needs_project_or_age(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        cli.main(["clean"])
