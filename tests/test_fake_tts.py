"""P0.1: голос fake — детерминированный, офлайн, с паузами и таймкодами слов."""
import hashlib
import json
import shutil
from pathlib import Path

from studio import project, timing, tts
from studio.textutil import segments, tts_text

FIXTURE = Path(__file__).parent / "fixtures" / "fake_tts"
CFG = {"backend": "fake", "voice": "fake"}
LINE = "People say | it takes three weeks to build a habit, really."


def _synth(tmp_path, line=LINE, rate=100):
    beats = [tts_text(s) for s in segments(line)]
    return tts.synth(tts_text(line), CFG, rate, tmp_path, beats=beats)


def test_bytes_are_stable(tmp_path):
    # Якорь кросс-платформенности: те же байты на Windows и Linux (CI, P0.7). Менять — только осознанно.
    wav = _synth(tmp_path)
    digest = hashlib.sha1(wav.read_bytes() + wav.with_suffix(".words.json").read_bytes()).hexdigest()
    assert digest == "6bdade0eb31bc4af3c3b0c2588841025f3b8e472"


def test_words_and_pauses(tmp_path):
    wav = _synth(tmp_path)
    words = tts.load_words(wav)
    assert [w for w, _, _ in words] == tts_text(LINE).split()
    assert all(a < b for _, a, b in words)
    assert all(words[i][2] <= words[i + 1][1] for i in range(len(words) - 1))
    dur = tts.duration(wav)
    assert abs(words[-1][2] - dur) < 1e-3  # хвост без тишины, как после TRIM
    sil = tts.silences(tts.read_wav(wav))
    gaps = [(words[i][2], words[i + 1][1]) for i in range(len(words) - 1)]
    # пауза на '|' (после «say») и на запятой (после «habit,»)
    for i in (1, 9):
        a, b = gaps[i]
        assert any(abs(s0 - a) < 0.02 and abs(s1 - b) < 0.02 for s0, s1 in sil), (i, gaps[i], sil)
    assert len(sil) == 2  # межсловные зазоры паузами не считаются


def test_split_bounds_snap_to_beat_pause(tmp_path):
    wav = _synth(tmp_path)
    words = tts.load_words(wav)
    x = tts.read_wav(wav)
    bounds = timing._split_bounds(segments(LINE), len(x) / tts.SR, tts.silences(x))
    assert abs(bounds[0][1] - words[1][2]) < 0.02 and abs(bounds[1][0] - words[2][1]) < 0.02


def test_rate_scales_duration(tmp_path):
    slow = tts.duration(_synth(tmp_path / "a", rate=100))
    fast = tts.duration(_synth(tmp_path / "b", rate=125))
    assert abs(fast / slow - 0.8) < 0.01


def test_cache_key_of_other_backends_unchanged():
    # beats входят в ключ только у fake: кэш (и деньги) живых бэкендов не трогаем
    for be in ("rhvoice", "edge", "piper", "elevenlabs"):
        cfg = {"backend": be, "voice": "v"}
        assert tts.cache_key("a b", cfg, 100) == tts.cache_key("a b", cfg, 100, beats=["a", "b"])


def _layout(dst):
    shutil.copytree(FIXTURE, dst)
    proj = project.load(dst)
    assert proj.cfg["tts"]["voice"] == "fake"
    timing.layout(proj, log=lambda *_: None)
    return (dst / "build" / "timeline.json").read_text(encoding="utf-8")


def test_layout_is_deterministic(tmp_path):
    a, b = _layout(tmp_path / "a"), _layout(tmp_path / "b")
    assert a == b
    tl = json.loads(a)
    assert tl["backend"] == "fake"
    words = [w["w"] for s in tl["scenes"] for w in s["words"]]
    assert "habit." in words and "myth." in words
    assert 120 < tl["wpm_speech"] < 200
