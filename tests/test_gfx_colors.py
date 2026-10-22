"""P0.3: gfx — цвета настроения и свечение главы."""
import pytest

from studio import gfx
from studio import style as SM

NEON = gfx.PALETTES["neon"]


@pytest.fixture
def pal(monkeypatch):
    st = SM.Style("neon", overrides=(("glow_cool", "#010101"), ("glow_warm", "#020202")))
    monkeypatch.setattr(SM, "_active", st)  # активный стиль процесса после теста — прежний
    return st.pal


def test_hex_rgb():
    assert gfx.hex_rgb("#FFaa00") == (255, 170, 0)
    assert gfx.hex_rgb(" 0a0b0c ") == (10, 11, 12)
    for bad in ("#fff", "#gg0000", "", "#1234567"):
        with pytest.raises(ValueError):
            gfx.hex_rgb(bad)


def test_mood_colors_default_is_palette_accents():
    assert gfx.mood_colors(base=NEON) == {"glow_cool": NEON["accent"], "glow_warm": NEON["accent2"],
                                          "accent2": NEON["accent2"]}


def test_mood_colors_uses_global_palette(pal):
    assert gfx.mood_colors()["glow_cool"] == NEON["accent"]


@pytest.mark.parametrize("mood", sorted(gfx.MOODS))
def test_mood_colors_mood(mood):
    assert gfx.mood_colors(mood, base=NEON) == gfx.MOODS[mood]


def test_mood_colors_overrides_win():
    got = gfx.mood_colors("ember", {"accent2": "#010203"}, base=NEON)
    assert got == dict(gfx.MOODS["ember"], accent2=(1, 2, 3))


def test_mood_colors_errors():
    with pytest.raises(ValueError, match="нет настроения"):
        gfx.mood_colors("sunny", base=NEON)
    with pytest.raises(ValueError, match="style.overrides.accent"):
        gfx.mood_colors(None, {"accent": "#000000"}, base=NEON)
    with pytest.raises(ValueError):
        gfx.mood_colors(None, {"accent2": "red"}, base=NEON)


def test_chapter_glow(pal):
    for empty in (None, "", {}):
        assert gfx.chapter_glow(empty) is None
    m = gfx.MOODS["night"]
    assert gfx.chapter_glow("night") == (m["glow_cool"], m["glow_warm"])
    assert gfx.chapter_glow({"cool": "#000001", "warm": "#000002"}) == ((0, 0, 1), (0, 0, 2))
    # недостающий цвет — из текущей палитры
    assert gfx.chapter_glow({"cool": "#000001"}) == ((0, 0, 1), (2, 2, 2))
    assert gfx.chapter_glow({"warm": "#000002"}) == ((1, 1, 1), (0, 0, 2))


def test_chapter_glow_falls_back_to_accents(monkeypatch):
    monkeypatch.setattr(SM, "_active", SM.Style("neon"))  # без настроения: glow_* = accent / accent2
    assert gfx.chapter_glow({"cool": "#000001"}) == ((0, 0, 1), NEON["accent2"])


def test_chapter_glow_errors(pal):
    for bad in ({"cool": "#000001", "hot": "#000002"}, 5, ["night"]):
        with pytest.raises(ValueError, match="glow"):
            gfx.chapter_glow(bad)
    with pytest.raises(ValueError, match="нет настроения"):
        gfx.chapter_glow("sunny")
