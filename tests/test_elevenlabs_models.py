"""ElevenLabs по моделям (docs/ELEVENLABS.md): v4 понимает только stability и similarity_boost — лишнее не шлём,
а validate говорит, что темп и style на v4 не подействуют. Сеть не трогаем: `_el_request` подменён."""
import base64
from types import SimpleNamespace

import pytest

from studio import tts
from studio import validate as V


@pytest.fixture
def sent(monkeypatch, tmp_path):
    bodies = []

    def fake(path, body=None, method="GET", ws=None):
        bodies.append(body)
        return {"audio_base64": base64.b64encode(b"\0" * 2000).decode(), "alignment": {}}

    monkeypatch.setattr(tts, "_el_request", fake)

    def call(cfg, rate=110):
        tts._elevenlabs("Привет.", "voice-id", rate, tmp_path / "x.mp3", cfg=cfg)
        return bodies[-1]
    return call


def test_v2_sends_all_settings(sent):
    b = sent({"model": "eleven_multilingual_v2"})
    assert set(b["voice_settings"]) == set(tts.EL_SETTINGS)
    assert b["voice_settings"]["speed"] == pytest.approx(1.1)


@pytest.mark.parametrize("model", ["eleven_v4", "eleven_v4_turbo"])
def test_v4_sends_only_stability_and_similarity(sent, model):
    b = sent({"model": model, "style": 0.3, "speed": 1.1})
    assert b["model_id"] == model
    assert set(b["voice_settings"]) == {"stability", "similarity_boost"}


def test_v3_keeps_speed_drops_style(sent):
    assert set(sent({"model": "eleven_v3"})["voice_settings"]) == {"stability", "similarity_boost", "speed"}


def test_settings_filter_keeps_cache_key():
    """Фильтр — только в теле запроса: ключ кэша прежний, готовая озвучка v2-проектов не пересинтезируется."""
    cfg = {"backend": "elevenlabs", "voice": "v", "model": "eleven_v4"}
    assert "style" in tts.el_call_cfg(cfg)  # в ключ кэша по-прежнему входит всё


def proj(**tts_cfg):
    return SimpleNamespace(cfg={"tts": {"backend": "elevenlabs", "rate_range": [98, 125], **tts_cfg}})


def test_post_tempo_only_without_api_speed():
    """v4 без speed в API: темп rate/100 (или voice.speed) — после синтеза; v2 и v3 — в запросе, после — 1."""
    assert tts.el_post_tempo({"model": "eleven_v4"}, 120) == pytest.approx(1.2)
    assert tts.el_post_tempo({"model": "eleven_v4", "speed": 1.05}, 120) == pytest.approx(1.05)
    assert tts.el_post_tempo({"model": "eleven_v4"}, 140) == pytest.approx(1.2)  # потолок API 1,2
    assert tts.el_post_tempo({"model": "eleven_multilingual_v2"}, 120) == 1.0
    assert tts.el_post_tempo({"model": "eleven_v3"}, 120) == 1.0
    assert tts.el_post_tempo({}, 110) == 1.0  # модель по умолчанию — v2


def test_post_tempo_in_cache_key_only_for_v4():
    v2 = {"backend": "elevenlabs", "voice": "v"}
    v4 = dict(v2, model="eleven_v4")
    assert tts.cache_key("Текст.", v4, 120) != tts.cache_key("Текст.", v4, 110)
    assert tts.cache_key("Текст.", v4, 100) != tts.cache_key("Текст.", dict(v4, model="eleven_v4x"), 100)
    assert tts.cache_key("Текст.", v2, 110) == tts.cache_key("Текст.", dict(v2), 110)


@pytest.fixture
def tone_backend(monkeypatch):
    """Фальшивый ElevenLabs: 2 с тона без тишины и слово на 1,0–1,5 с — как таймкоды из ответа API."""
    import numpy as np

    def fake(text, voice, rate, out_raw, cfg=None, ws=None):
        t = np.arange(int(tts.SR * 2.0)) / tts.SR
        tts.write_wav(out_raw, 0.3 * np.sin(2 * np.pi * 220 * t).astype(np.float32))
        tts._RAW_WORDS[str(out_raw)] = [["слово", 1.0, 1.5]]

    monkeypatch.setitem(tts.BACKENDS, "elevenlabs", fake)


@pytest.mark.parametrize("model, k", [("eleven_v4", 1.2), ("eleven_multilingual_v2", 1.0)])
def test_synth_post_tempo_shortens_audio_and_words(tone_backend, tmp_path, model, k):
    cfg = {"backend": "elevenlabs", "voice": "v", "model": model}
    wav = tts.synth("Текст.", cfg, 120, tmp_path)
    assert tts.duration(wav) == pytest.approx(2.0 / k, abs=0.03)
    (w, t0, t1), = tts.load_words(wav)
    assert t0 == pytest.approx(1.0 / k, abs=0.02) and t1 == pytest.approx(1.5 / k, abs=0.02)


def test_validate_voice_override_on_v4_warns():
    e, w = [], []
    V.voice(proj(model="eleven_v4"), {"style": 0.3, "stability": 0.4}, "ch01/s01", e, w)
    assert not e and any("voice.style" in x and "не подействует" in x for x in w)
    e, w = [], []
    V.voice(proj(), {"style": 0.3}, "ch01/s01", e, w)  # v2 — style есть
    assert not e and not any("не подействует" in x for x in w)
    e, w = [], []
    V.voice(proj(model="eleven_v4"), {"speed": 1.1}, "ch01/s01", e, w)  # speed на v4 — atempo после синтеза
    assert not e and not any("не подействует" in x for x in w)


def test_validate_line_markup(tmp_path):
    """Теги по-русски, `+` RHVoice и <break> — предупреждения; английский тег на v4 — без «прочитан вслух»."""
    import shutil
    from pathlib import Path

    import yaml

    from studio.project import load

    root = tmp_path / "p"
    shutil.copytree(Path(__file__).parent / "fixtures" / "fake_tts", root)
    pf = root / "project.yaml"
    cfg = yaml.safe_load(pf.read_text(encoding="utf-8"))
    cfg["tts"] = {"backend": "elevenlabs", "voice": "voice-x", "rate": 100, "model": "eleven_v4"}
    pf.write_text(yaml.safe_dump(cfg, allow_unicode=True), encoding="utf-8")
    sf = root / "script" / "ch01.yaml"
    d = yaml.safe_load(sf.read_text(encoding="utf-8"))
    d["scenes"][0]["lines"] = ["[dry, wry] A tag in English.", "[шёпотом] A tag in Russian.",
                               "Stress z+amok here.", 'Wait <break time="1s"/> here.']
    sf.write_text(yaml.safe_dump(d, allow_unicode=True), encoding="utf-8")
    w = "\n".join(V.check(load(root)).warns)
    assert "прочитан вслух" not in w           # [dry, wry] на v4 — законный тег
    assert "тег по-русски" in w and "«+»" in w and "<break>" in w
    assert "не подействует" not in w           # rate 100 на v4 — без предупреждения
