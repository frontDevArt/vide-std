"""P4.4: дорожка голоса и SFX собирается кусками — память не растёт с длиной ролика, звук тот же, что был."""
import tracemalloc
import wave

import numpy as np

from conftest import make_gallery
from studio import audio, project, sfx as FX, timing, tts as T
from studio.timing import load_timeline


def _old_voice(proj, tl):
    """Сборка до P4.4: весь ролик float32 в RAM — эталон звука."""
    SR = T.SR
    n = int(round(tl["total_frames"] * SR / tl["fps"]))
    x = np.zeros(n, np.float32)
    for s in tl["scenes"]:
        base = s["start_frame"] * SR // tl["fps"]
        for L in s["lines"]:
            y = T.read_wav(proj.bdir("tts") / L["wav"])
            a = base + int(round(L["t0"] * SR))
            b = min(n, a + len(y))
            x[a:b] += y[: b - a]
    ev = audio.sfx_events(proj, tl)
    act = x[np.abs(x) > 1e-3]
    rms = float(np.sqrt(np.mean(act ** 2)))
    out = np.zeros(n, np.float32)
    for t, name in ev:
        y = FX.make(name) * rms * 10 ** (FX.LEVEL.get(name, -30) / 20)
        a = int(round(t * SR))
        b = min(n, a + len(y))
        out[a:b] += y[: b - a]
    x += out
    return ev, (np.clip(x, -1, 1) * 32767).astype(np.int16)


def _read(path):
    with wave.open(str(path), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def test_same_sound_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "BLOCK", 7919)  # мелкие куски: строки и звуки режутся границами
    proj = project.load(make_gallery(tmp_path / "gallery", "horizontal"))
    timing.layout(proj, log=lambda *_: None)
    tl = load_timeline(proj)
    ev, ref = _old_voice(proj, tl)
    assert ev, "в gallery есть шаблоны lab со звуками"
    got = _read(audio.voice_track(proj, tl, tmp_path))
    assert len(got) == len(ref)
    # RMS речи теперь копится во float64 по кускам: расхождение — не больше младшего бита на редком сэмпле
    assert int(np.abs(got.astype(np.int32) - ref).max()) <= 1


def _peak(tmp_path, monkeypatch, minutes):
    """Пик памяти voice_track на синтетике: строка 4 с и звук «pop» каждые 5 с."""
    SR, fps, k = T.SR, 30, minutes * 12
    root = tmp_path / f"m{minutes}"
    cache = root / "build" / "tts"
    cache.mkdir(parents=True)
    T.write_wav(cache / "a.wav", 0.3 * np.sin(np.arange(SR * 4) / 9).astype(np.float32))
    tl = {"fps": fps, "total_frames": k * 150,
          "scenes": [{"start_frame": i * 150, "lines": [{"wav": "a.wav", "t0": 0.3}]} for i in range(k)]}

    class P:
        cfg = {}
        def bdir(self, name):
            return root / "build" / name

    monkeypatch.setattr(audio, "sfx_events", lambda proj, tl: [(i * 5.0 + 0.1, "pop") for i in range(k)])
    tracemalloc.start()
    try:
        path = audio.voice_track(P(), tl, root)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert len(_read(path)) == k * 150 * SR // fps
    return peak


def test_memory_does_not_grow_with_length(tmp_path, monkeypatch):
    """До P4.4 пик рос с длиной: ~3,5 × float32 на весь ролик (10 мин — 385 МБ, час — 2,3 ГБ)."""
    p5, p20 = _peak(tmp_path, monkeypatch, 5), _peak(tmp_path, monkeypatch, 20)
    full20 = 20 * 60 * T.SR * 4
    assert p20 < 1.2 * p5, f"пик растёт с длиной: 5 мин — {p5 / 2**20:.0f} МБ, 20 мин — {p20 / 2**20:.0f} МБ"
    assert p20 < 0.15 * full20, f"пик {p20 / 2**20:.0f} МБ при {full20 / 2**20:.0f} МБ float32 на 20 минут"
