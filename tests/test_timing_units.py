"""P0.3: timing — границы битов по паузам, базовая длительность, подбор темпа (без синтеза)."""
from types import SimpleNamespace

import pytest

from studio import timing
from studio.timing import _split_bounds, base_total, choose_rate

PAUSES = {"start": 0.4, "end": 0.8, "scene": 0.6, "comma": 0.25, "sentence": 0.45}


# ---------------------------------------------------------------- _split_bounds
def test_split_bounds_single_segment():
    assert _split_bounds(["one"], 1.23456, [(0.5, 0.7)]) == [(0.0, 1.23456)]


def test_split_bounds_without_pauses_follows_weights():
    assert _split_bounds(["aa", "aa"], 2.0, []) == [(0.0, 1.0), (1.0, 2.0)]
    # вес 1 : 3 -> граница на четверти
    assert _split_bounds(["a", "aaa"], 2.0, []) == [(0.0, 0.5), (0.5, 2.0)]


def test_split_bounds_snaps_to_pause_in_window():
    # оценка 1.0, окно max(0.18, min(0.45, 0.12*dur)) = 0.24
    assert _split_bounds(["aa", "aa"], 2.0, [(0.9, 1.2)]) == [(0.0, 0.9), (1.2, 2.0)]
    assert _split_bounds(["aa", "aa"], 2.0, [(1.5, 1.6)]) == [(0.0, 1.0), (1.0, 2.0)]  # далеко — не берём


def test_split_bounds_prefers_longer_pause():
    sil = [(0.95, 1.0), (1.05, 1.25)]
    assert _split_bounds(["aa", "aa"], 2.0, sil) == [(0.0, 1.05), (1.25, 2.0)]


def test_split_bounds_uses_each_pause_once():
    # веса 1, 1, 4 при dur 3: оценки 0.5 и 1.0; одна пауза в окне обеих — достаётся первой границе
    assert _split_bounds(["a", "a", "aaaa"], 3.0, [(0.7, 0.8)]) == [(0.0, 0.7), (0.8, 1.0), (1.0, 3.0)]


def test_split_bounds_rounds_to_ms():
    b = _split_bounds(["aa", "aa"], 2.0, [(0.91234, 1.18765)])
    assert b == [(0.0, 0.912), (1.188, 2.0)]


# ---------------------------------------------------------------- base_total
def _proj(**cfg):
    return SimpleNamespace(cfg={"pauses": dict(PAUSES), **cfg})


def _line(dur, pause_after=0.3):
    return {"dur": dur, "pause_after": pause_after}


def test_base_total_single_scene():
    voiced = [("ch01", {}, [_line(1.0, 0.3), _line(2.0, 0.5)])]
    assert base_total(_proj(), voiced) == pytest.approx(0.4 + 3.3 + 0.8)  # пауза после последней строки не в счёт


def test_base_total_pauses_hold_min_duration():
    voiced = [
        ("ch01", {}, [_line(1.0, 0.3), _line(2.0, 0.5)]),      # 0.4 + 3.3 + 0.3
        ("ch01", {"hold": 0.5}, [_line(1.0, 9.0)]),           # 0.3 + 1.0 + 0.3 + 0.5
        ("ch02", {"min_duration": 5}, []),                    # max(0.3 + 0 + 0.8, 5)
    ]
    assert base_total(_proj(), voiced) == pytest.approx(4.0 + 2.1 + 5.0)


# ---------------------------------------------------------------- choose_rate
@pytest.fixture
def fake_measure(monkeypatch):
    """Речь 10 с при темпе 100, обратно пропорционально темпу; паузы start+end = 1 с."""
    calls = []

    def measure(proj, rate):
        calls.append(rate)
        return [("ch01", {}, [_line(10.0 * 100 / rate)])]
    monkeypatch.setattr(timing, "measure", measure)
    return calls


def _rate_proj(target=None, **tts):
    p = _proj(target_duration=target, tts={"rate_range": [98, 125], **tts})
    p.cfg["pauses"].update(start=0.5, end=0.5)
    return p


def test_choose_rate_fixed_number(fake_measure):
    r, voiced = choose_rate(_rate_proj(rate=110), log=lambda *_: None)
    assert r == 110.0 and isinstance(r, float)
    assert fake_measure == [110.0] and voiced[0][2][0]["dur"] == pytest.approx(1000 / 110)


def test_choose_rate_auto_without_target(fake_measure):
    r, _ = choose_rate(_rate_proj(rate="auto"), log=lambda *_: None)
    assert r == 105.0 and fake_measure == [105.0]


def test_choose_rate_fits_at_lower_bound(fake_measure):
    r, _ = choose_rate(_rate_proj(target=12, rate="auto"), log=lambda *_: None)
    assert r == 98.0 and fake_measure == [98.0]


def test_choose_rate_speeds_up_within_range(fake_measure):
    log = []
    r, voiced = choose_rate(_rate_proj(target=10, rate="auto"), log=log.append)
    assert fake_measure == [98.0, 115]
    assert r == 115 and base_total(_rate_proj(), voiced) <= 10 - 0.15
    assert len(log) == 2 and "цель 10" in log[-1]


def test_choose_rate_refuses_to_cut_speech(fake_measure):
    with pytest.raises(SystemExit, match="Сократите текст"):
        choose_rate(_rate_proj(target=8, rate="auto"), log=lambda *_: None)
    assert fake_measure[-1] == 125  # дошли до потолка rate_range и не дальше
    assert max(fake_measure) <= 125
