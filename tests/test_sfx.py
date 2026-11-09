"""Звуки появления studio/sfx.py: каждое имя из LEVEL синтезируется (не тишина), RMS = 1 — уровень задаёт LEVEL."""
import numpy as np

from studio import sfx as FX


def test_every_level_name_has_sound():
    for name in FX.LEVEL:
        y = FX.make(name)
        assert len(y) > FX.SR * 0.03, name
        assert abs(float(np.sqrt(np.mean(y.astype(np.float64) ** 2))) - 1) < 1e-3, name


def test_track_places_paper_sounds():
    ev = [(0.5, "paper"), (1.0, "stamp")]
    x = FX.track(FX.SR * 2, ev, voice_rms=0.1)
    assert not x[: int(FX.SR * 0.49)].any() and x[int(FX.SR * 0.5):int(FX.SR * 0.6)].any()
    assert np.abs(x[int(FX.SR * 1.0):int(FX.SR * 1.1)]).max() > np.abs(x[int(FX.SR * 0.5):int(FX.SR * 0.6)]).max()
