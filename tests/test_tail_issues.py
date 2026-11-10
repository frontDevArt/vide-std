"""tts.tail_issues — хвост фразы для qa «Стыки речи» (2026-11-09): чистое затухание, обрыв, чужое начало после
тишины (ElevenLabs с контекстом соседних строк) и смычка «т» в конце слова, которую ловить нельзя."""
import numpy as np

from studio import qa, tts as T

SR = T.SR
RNG = np.random.default_rng(7)


def _tone(dur, db=0.0):
    t = np.arange(int(SR * dur)) / SR
    return (0.3 * 10 ** (db / 20) * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _noise(dur, db):
    return (0.3 * 10 ** (db / 20) * RNG.standard_normal(int(SR * dur))).astype(np.float32)


def _decay(dur):  # затухание до тишины — как после среза хвоста −60 dB и гашения 50 мс
    y = _tone(dur)
    return (y * np.exp(-np.arange(len(y)) / SR * 25)).astype(np.float32)


def test_clean_decay_is_ok():
    assert T.tail_issues(np.concatenate([_tone(1.0), _decay(0.25)])) == []


def test_abrupt_end_is_clip():
    assert T.tail_issues(_tone(1.2)) == ["clip"]


def test_onset_after_silence_is_bleed():
    x = np.concatenate([_tone(1.0), _decay(0.2), np.zeros(int(SR * 0.15), np.float32), _tone(0.04, -6)])
    assert T.tail_issues(x) == ["clip", "bleed"]  # чужое начало обрезано на полуслове — и обрыв тоже


def test_final_stop_release_is_not_bleed():
    # «…лимит.»: смычка 40 мс на −45 dB, потом взрыв «т» и его затухание — естественный конец слова
    burst = _noise(0.1, -6) * np.exp(-np.arange(int(SR * 0.1)) / SR * 60).astype(np.float32)
    x = np.concatenate([_tone(1.0), _decay(0.08), _noise(0.04, -45), burst])
    assert T.tail_issues(x) == []


def test_short_line_is_skipped():
    assert T.tail_issues(_tone(0.05)) == []


def test_min_gap_by_seam():
    # тишина до следующей фразы: склейка сцен > конец предложения > запятая/тире (0,26 с после точки — мало)
    assert qa.min_gap("Клод не помнит чат.", scene_cut=True) == qa.MIN_GAP["scene"]
    assert qa.min_gap("Клод не помнит чат.", scene_cut=False) == qa.MIN_GAP["sentence"] > 0.26
    assert qa.min_gap("И Клод спрашивает карту,", scene_cut=False) == qa.MIN_GAP["comma"]
    assert qa.min_gap("В тестах авторов —", scene_cut=False) == qa.MIN_GAP["comma"]
