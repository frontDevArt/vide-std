"""P0.3: субтитры — перенос и нарезка сцены. Моноширинный «шрифт»: результат не зависит от Pillow и системы."""
from types import SimpleNamespace

import pytest

from studio import subs


class Mono:
    def __init__(self, px):
        self.px = px

    def getlength(self, s):
        return len(s) * self.px


F = Mono(10)  # 10 символов = 100 px


# ---------------------------------------------------------------- wrap
def test_wrap_empty_and_fits():
    assert subs.wrap("", F, 100) == [] and subs.wrap("   ", F, 100) == []
    assert subs.wrap("short", F, 100) == ["short"]
    assert subs.wrap("exactly 10", F, 100) == ["exactly 10"]


def test_wrap_single_line_limit():
    assert subs.wrap("aaaa bbbb cccc", F, 100, max_lines=1) is None


def test_wrap_balanced_two_lines():
    # кандидаты (5, 8) и (8, 5) равны по max — берётся первый
    assert subs.wrap("aa bb cc dd ee", F, 100) == ["aa bb", "cc dd ee"]
    assert subs.wrap("one two three four", F, 100) == ["one two", "three four"]


def test_wrap_three_lines():
    t = "aaaa bbbb cccc dddd eeee"
    assert subs.wrap(t, F, 100) is None
    assert subs.wrap(t, F, 100, max_lines=3) == ["aaaa", "bbbb cccc", "dddd eeee"]


def test_wrap_word_wider_than_line():
    assert subs.wrap("abcdefghijkl x", F, 100, max_lines=3) is None


# ---------------------------------------------------------------- chunks_for_scene
@pytest.fixture
def proj(monkeypatch):
    monkeypatch.setattr(subs.gfx, "font", lambda size, weight="bold": Mono(20))
    # вертикаль 1080: max_width 928, минус 1.2*size -> 868 px = 43 символа
    return SimpleNamespace(size=(1080, 1920), cfg={"subtitles": {"size": 50, "max_lines": 2}})


def _beat(line, text, t0, t1):
    return {"line": line, "text": text, "t0": t0, "t1": t1}


def test_chunks_disabled(proj):
    proj.cfg["subtitles"]["enabled"] = False
    assert subs.chunks_for_scene(proj, {"beats": [_beat(0, "a", 0, 1)], "dur": 2}) == []


def test_chunks_lead_and_hold(proj):
    sc = {"beats": [_beat(0, "Short one.", 0.0, 1.0), _beat(1, "Next.", 2.0, 3.0)], "dur": 4.0}
    assert subs.chunks_for_scene(proj, sc) == [
        {"lines": ["Short one."], "t0": 0.0, "t1": 1.35},   # раньше звука на 0.05 (не < 0), держим +0.35
        {"lines": ["Next."], "t0": 1.95, "t1": 3.35},
    ]


def test_chunks_short_gap_holds_until_next(proj):
    sc = {"beats": [_beat(0, "One.", 0.0, 1.0), _beat(1, "Two.", 1.2, 2.0)], "dur": 2.1}
    c = subs.chunks_for_scene(proj, sc)
    assert c[0]["t1"] == 1.13  # 1.2 - 0.05 - 0.02: без мигания
    assert c[1]["t1"] == 2.05  # конец сцены - 0.05


def test_chunks_minimum_duration(proj):
    sc = {"beats": [_beat(0, "Hi.", 1.0, 1.05)], "dur": 1.2}
    # минимум 0.3 с от начала звука (не субтитра) — даже за концом сцены
    assert subs.chunks_for_scene(proj, sc) == [{"lines": ["Hi."], "t0": 0.95, "t1": 1.3}]


def test_chunks_merge_short_beats_of_one_line(proj):
    sc = {"beats": [_beat(0, "So,", 0.0, 0.3), _beat(0, "what now?", 0.35, 1.2), _beat(1, "Yes.", 1.3, 1.5)],
          "dur": 3.0}
    c = subs.chunks_for_scene(proj, sc)
    assert [x["lines"] for x in c] == [["So, what now?"], ["Yes."]]  # «Yes.» короткий, но другая строка


def test_chunks_split_long_beat(proj):
    words = " ".join(f"word{i:02d}" for i in range(20))  # 139 символов > 2 строк по 43
    c = subs.chunks_for_scene(proj, {"beats": [_beat(0, words, 1.0, 8.0)], "dur": 9.0})
    assert len(c) == 2
    assert all(x["lines"] and len(x["lines"]) <= 2 for x in c)
    assert " ".join(" ".join(x["lines"]) for x in c) == words
    assert c[0]["t0"] == 0.95 and c[0]["t1"] < c[1]["t0"] + 0.1 and c[-1]["t1"] <= 9.0


def test_srt_timestamp():
    assert subs._ts(0) == "00:00:00,000"
    assert subs._ts(3725.0464) == "01:02:05,046"
    assert subs._ts(1.9995, ".") == "00:00:02.000"  # округление, а не отбрасывание


def test_chunks_split_tail_does_not_overlap_next(proj):
    # fake-discounts, 9:16: длинный бит режется, хвост «Friday» ~0,1 с — минимум 0,3 с не должен заходить на следующий
    proj.cfg["subtitles"]["max_lines"] = 1
    long = "What's the one deal you bought on Black Friday"  # 46 символов > 43: хвост — одно слово
    sc = {"beats": [_beat(0, long, 1.0, 2.0), _beat(0, "that you later saw cheaper?", 2.0, 3.5)], "dur": 4.0}
    c = subs.chunks_for_scene(proj, sc)
    assert len(c) == 3
    assert all(a["t1"] <= b["t0"] + 1e-9 for a, b in zip(c, c[1:])), c
