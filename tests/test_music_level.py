"""Музыка от голоса (music.under_lu, studio/audio.py → music_relative) и ИИ-трек (studio/musicgen.py).

Уровень музыки — в LU от голоса в полосе речи, не сдвигом файла: тихий и плотный трек дают одно и то же; приглушение —
по сценарию (заранее до слога, без «качелей» в коротких паузах)."""
import io
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import yaml

from studio import audio, musicgen, project, timing, validate
from studio import music as M
from studio.tts import SR

FIX = Path(__file__).parent / "fixtures"


def _quiet(*_a, **_k):
    pass


def _proj(tmp_path, name="p", **music):
    dst = tmp_path / name
    shutil.copytree(FIX / "fake_tts", dst)
    p = dst / "project.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8"))
    d["music"] = music
    p.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    return dst


def _noise(path, peak, sec=4.0, seed=1):
    y = np.random.default_rng(seed).standard_normal((int(sec * SR), 2))
    M._write(path, y / np.abs(y).max() * peak)
    return path


def test_speech_regions_merge_short_pauses():
    s = lambda t: int(t * SR)  # noqa: E731
    spans = [(s(0.2), s(1.0)), (s(1.5), s(2.0)), (s(3.5), s(4.0))]  # паузы 0,5 и 1,5 с
    assert audio.speech_regions(spans, 0.9) == [(s(0.2), s(2.0)), (s(3.5), s(4.0))]
    assert len(audio.speech_regions(spans, 0.3)) == 3


def test_duck_curve_lookahead_and_release():
    a, b = SR, 2 * SR
    s = audio.duck_curve([(a, b)], 0, 4 * SR)
    at = lambda t: s[int(round(t * SR))]  # noqa: E731
    assert at(1.0 - audio.LOOKAHEAD) > 0.999                       # первый слог — уже под приглушённой музыкой
    assert at(1.0 - audio.LOOKAHEAD - audio.ATTACK - 0.01) < 1e-6  # раньше — музыка открыта
    assert at(2.0 + audio.RELEASE_DELAY) > 0.999                    # хвост слова не подхватывает музыку
    assert at(2.0 + audio.RELEASE_DELAY + audio.RELEASE + 0.01) < 1e-6
    rise = s[:a]
    assert np.all(np.diff(rise) >= -1e-12)                          # вниз — монотонно, без щелчков


@pytest.mark.parametrize("peak", [0.9, 0.05])
def test_under_level_follows_voice_not_file(tmp_path, peak):
    """Плотный трек (пик 0,9) и тихий (0,05, −25 dB) — одна и та же громкость под речью."""
    root = _proj(tmp_path, file="assets/m.wav", under_lu=-15)
    (root / "assets").mkdir()
    _noise(root / "assets" / "m.wav", peak)
    proj = project.load(root)
    timing.layout(proj, log=_quiet)
    out = tmp_path / "o"
    out.mkdir()
    assert Path(audio.mix(proj, out, log=_quiet)).exists()
    lv = json.loads((proj.bdir("mix") / "levels.json").read_text(encoding="utf-8"))
    assert lv["mode"] == "under_lu" and lv["under_lu"] == -15
    assert abs(lv["under_actual"] - (-15)) <= 1.0, lv
    assert lv["clipped"] == 0


def test_validate_warns_on_extreme_levels(tmp_path):
    loud = validate.check(project.load(_proj(tmp_path, "a", under_lu=-6)))
    assert any("−10" in w for w in loud.warns)
    stray = validate.check(project.load(_proj(tmp_path, "b", open_lu=-6)))
    assert any("только при under_lu" in w for w in stray.warns)


def test_musicgen_plan_compose_record(tmp_path, monkeypatch):
    root = _proj(tmp_path, generate={"model": "music_v2_5", "prompts": {"a": "synthwave, no vocals"}})
    proj = project.load(root)
    with pytest.raises(musicgen.MusicUnavailable):  # длина — по таймлайну: до voice трека не заказать
        musicgen.plan(proj)
    timing.layout(proj, log=_quiet)
    assert musicgen.issues(proj) == []
    (job,) = musicgen.plan(proj)
    assert job.out.parent == root / "assets" / "music" and job.out.name.startswith("a-")
    assert job.ms % 100 == 0 and job.credits == -(-job.ms * musicgen.CREDITS_PER_MIN // 60000)
    sent = {}

    class Resp(io.BytesIO):
        headers = {"song-id": "abc123"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_open(req, timeout):
        sent.update(json.loads(req.data), url=req.full_url)
        return Resp(b"\xff" * 20000)
    monkeypatch.setattr("studio.tts._el_urlopen", fake_open)
    monkeypatch.setattr("studio.tts._el_key", lambda ws=None: "k")
    got = musicgen.compose(job)
    assert sent["force_instrumental"] is True and sent["music_length_ms"] == job.ms and "/music?" in sent["url"]
    assert job.out.exists() and got["song_id"] == "abc123"
    rec = musicgen.record(proj, job, got["song_id"], "starter")
    assert rec["file"] == f"assets/music/{job.out.name}" and "starter" in rec["license"] and rec["source"]
    bad = project.load(_proj(tmp_path, "c", generate={"model": "v9", "prompts": {}}))
    assert len(musicgen.issues(bad)) == 2
