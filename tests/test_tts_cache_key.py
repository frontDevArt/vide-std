"""P0.3: ключ кэша TTS. Поменялся ключ — весь кэш озвучки устарел, ElevenLabs синтезирует заново за деньги.
Якоря ниже менять только осознанно (и сказать об этом в коммите)."""
import pytest

from studio import tts
from studio.project import stable_hash

TEXT = "It takes sixty-six days, not twenty-one."
EL = {"backend": "elevenlabs", "voice": "VOICEID", "model": "eleven_multilingual_v2"}
PREV, NXT = "Everyone says three weeks.", "Here is why."


@pytest.mark.parametrize("backend, key", [
    ("fake", "7cb33de958c82b22"),
    ("rhvoice", "8294ca17452c9e6c"),
    ("edge", "a23aa80fc24a0e51"),
    ("piper", "5559362adcb5b134"),
])
def test_key_anchor_offline(backend, key):
    assert tts.cache_key(TEXT, {"backend": backend, "voice": "v1"}, 105) == key


def test_key_anchor_fake_beats():
    beats = ["It takes sixty-six days,", "not twenty-one."]
    assert tts.cache_key(TEXT, {"backend": "fake", "voice": "fake"}, 105, beats=beats) == "2522d41e6475344e"


def test_key_anchor_elevenlabs():
    assert tts.cache_key(TEXT, EL, 105) == "d8f3e706d2d4863d"
    assert tts.cache_key(TEXT, EL, 105, PREV, NXT, {"style": 0.3}) == "fb6f39b2e30651ec"


def test_stable_hash_ignores_dict_order():
    assert stable_hash({"a": 1, "b": [1, "ж"]}) == stable_hash({"b": [1, "ж"], "a": 1})
    assert len(stable_hash("x")) == 12 and len(stable_hash("x", 16)) == 16


def test_key_rate_rounding():
    cfg = {"backend": "edge", "voice": "v"}
    k = tts.cache_key(TEXT, cfg, 105)
    assert tts.cache_key(TEXT, cfg, 105.0) == k == tts.cache_key(TEXT, cfg, 105.04) == tts.cache_key(TEXT, cfg, "105")
    assert tts.cache_key(TEXT, cfg, 105.1) != k


def test_key_depends_on_text_voice_backend():
    k = tts.cache_key(TEXT, {"backend": "edge", "voice": "v"}, 105)
    assert tts.cache_key(TEXT + " ", {"backend": "edge", "voice": "v"}, 105) != k
    assert tts.cache_key(TEXT, {"backend": "edge", "voice": "w"}, 105) != k
    assert tts.cache_key(TEXT, {"backend": "piper", "voice": "v"}, 105) != k


def test_offline_key_ignores_context_and_extra_cfg():
    cfg = {"backend": "rhvoice", "voice": "v"}
    k = tts.cache_key(TEXT, cfg, 105)
    assert tts.cache_key(TEXT, dict(cfg, stability=0.9, rate_range=[90, 130]), 105, PREV, NXT, {"style": 1},
                         beats=["a"]) == k


def test_elevenlabs_key_context():
    base = tts.cache_key(TEXT, EL, 105)
    assert tts.cache_key(TEXT, EL, 105, PREV) != base
    assert tts.cache_key(TEXT, EL, 105, None, NXT) != base
    assert tts.cache_key(TEXT, EL, 105, PREV, NXT) != tts.cache_key(TEXT, EL, 105, NXT, PREV)
    assert tts.cache_key(TEXT, EL, 105, "", "") == base  # пустой сосед = нет соседа
    off = dict(EL, context=False)
    assert tts.cache_key(TEXT, off, 105, PREV, NXT) == tts.cache_key(TEXT, off, 105)


def test_elevenlabs_key_voice_settings():
    base = tts.cache_key(TEXT, EL, 105)
    # явное значение по умолчанию = отсутствие; модель по умолчанию тоже
    assert tts.cache_key(TEXT, dict(EL, stability=0.5), 105) == base
    assert tts.cache_key(TEXT, {k: v for k, v in EL.items() if k != "model"}, 105) == base
    assert tts.cache_key(TEXT, dict(EL, stability=0.4), 105) != base
    assert tts.cache_key(TEXT, EL, 105, voice={"stability": 0.5}) == base
    assert tts.cache_key(TEXT, EL, 105, voice={"speed": 1.1}) != base
    assert tts.cache_key(TEXT, EL, 105, voice={"pitch": 3}) == base  # чужие ключи override не влияют
    assert tts.cache_key(TEXT, dict(EL, rate_range=[90, 130], context=True), 105) == base
    assert tts.cache_key(TEXT, EL, 105, beats=["x"]) == base


def test_fake_key_beats():
    cfg = {"backend": "fake", "voice": "fake"}
    assert tts.cache_key(TEXT, cfg, 105) == tts.cache_key(TEXT, cfg, 105, beats=[])
    assert tts.cache_key(TEXT, cfg, 105, beats=["a", "b"]) != tts.cache_key(TEXT, cfg, 105, beats=["a b"])
    assert tts.cache_key(TEXT, cfg, 105, beats=("a", "b")) == tts.cache_key(TEXT, cfg, 105, beats=["a", "b"])
