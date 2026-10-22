"""P0.3: lab — разбор триггеров at: (бит, секунды, слово, n-е вхождение, последовательность)."""
import pytest

from studio import motion as M
from studio.lab import LabTemplate

LEAD = M.fr(M.F_LEAD)
WORDS = ["The", "median", "of", "66", "days.", "Median’s", "range,", "median,", "not", "mean."]
T0 = [0.5, 1.0, 1.4, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


@pytest.fixture
def tpl():
    scene = {"chapter": "ch01", "id": "s01", "dur": 6.0,
             "beats": [{"t0": 0.0, "t1": 1.9}, {"t0": 2.0, "t1": 5.5}],
             "words": [{"w": w, "t0": t, "t1": t + 0.3} for w, t in zip(WORDS, T0)]}
    return LabTemplate({"W": 1920, "H": 1080, "fps": 30, "language": "en"}, scene, {})


def test_none_and_bool_give_default(tpl):
    assert tpl.at(None, 7) == 7 and tpl.at(True, 7) == 7 and tpl.at(False) is None


def test_beat_index(tpl):
    assert tpl.at(1) == pytest.approx(2.0 - LEAD)
    assert tpl.at(-1) == pytest.approx(2.0 - LEAD)
    assert tpl.at(0) == 0.0  # не раньше начала сцены
    assert tpl.at(1, lead=False) == 2.0
    # бита нет: default, а без него — конец сцены (опережение вычитается и тут)
    assert tpl.at(5, 1.0) == pytest.approx(1.0 - LEAD)
    assert tpl.at(5) == pytest.approx(6.0 - LEAD)


def test_seconds(tpl):
    assert tpl.at(2.4) == 2.4  # float — время как есть, без опережения
    assert tpl.at("1.5s") == 1.5 and tpl.at(" 3s ") == 3.0


@pytest.mark.parametrize("spec, t", [
    ("66", 2.0),                 # строка-число — это слово, не бит
    ("median", 1.0),
    ("w:median", 1.0),
    ("MEDIAN", 1.0),
    ("days", 2.5),               # пунктуация слова не мешает
    ("median#2", 4.0),           # «Median’s» — другое слово
    ("median#", 1.0),
    ("median's", 3.0),           # типографский апостроф = обычный
    ("median of", 1.0),
    ("of 66 days.", 1.4),
    ("w:median, not#1", 4.0),
])
def test_word_triggers(tpl, spec, t):
    assert tpl.at(spec) == pytest.approx(t - LEAD)
    assert tpl.at(spec, lead=False) == t


@pytest.mark.parametrize("spec", ["median#3", "average", "mean. extra", "of days"])
def test_missing_word_warns_and_defaults(tpl, capsys, spec):
    assert tpl.at(spec, 9.0) == 9.0
    out = capsys.readouterr().out
    assert "ch01/s01" in out and spec in out


def test_lead_clamps_at_zero():
    scene = {"dur": 2.0, "beats": [{"t0": 0.0, "t1": 1.0}], "words": [{"w": "Go", "t0": 0.05, "t1": 0.3}]}
    tpl = LabTemplate({"W": 1080, "H": 1920, "fps": 30}, scene, {})
    assert tpl.at("go") == 0.0


def test_seq_times(tpl):
    items = [{"at": "median"}, {}, None, {"at": 1.25}]
    got = tpl.seq_times(items, 0.2)
    assert got[0] == pytest.approx(1.0 - LEAD)
    assert got[1] == pytest.approx(M.stagger(1, 0.2)) and got[2] == pytest.approx(M.stagger(2, 0.2))
    assert got[3] == 1.25
