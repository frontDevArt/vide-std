"""P0.3: textutil — сегменты '|', текст для TTS и субтитров, веса слогов."""
import pytest

from studio import textutil as tu
from studio.templates import plural


def test_line_text_and_voice():
    assert tu.line_text("Hi.") == "Hi."
    assert tu.line_text({"text": "Hi.", "voice": {"style": 0.4}}) == "Hi."
    assert tu.line_text({"voice": {}}) == ""
    assert tu.line_text(42) == "42"
    assert tu.line_voice("Hi.") == {}
    assert tu.line_voice({"text": "Hi.", "voice": None}) == {}
    v = {"style": 0.4}
    got = tu.line_voice({"text": "Hi.", "voice": v})
    assert got == v and got is not v  # копия: правка не портит сценарий


def test_segments():
    assert tu.segments("Каждый свайп: | смешное видео, | история.") == ["Каждый свайп:", "смешное видео,", "история."]
    assert tu.segments("No beats.") == ["No beats."]
    assert tu.segments(" | a || b | ") == ["a", "b"]
    assert tu.segments("") == []


def test_tts_text_keeps_stress_marks():
    assert tu.tts_text("Это  *важно* | для  з+амка.") == "Это важно для з+амка."
    assert tu.tts_text(" a|b ") == "a b"


def test_display_text_strips_markup_and_audio_tags():
    assert tu.display_text("[sighs] It's *fine* | for z+amka.") == "It's fine for zamka."
    assert tu.display_text("Say [whispers soft] it") == "Say it"
    assert tu.display_text("Keep [Capital] and [2x]") == "Keep [Capital] and [2x]"  # не тег eleven_v3


def test_weight():
    assert tu.weight("") == 0.5 and tu.weight("…") == 1.1 and tu.weight("ъ") == 0.5  # пол 0,5
    assert tu.weight("a") == 1.0
    assert tu.weight("bcdfg") == pytest.approx(1.4) and tu.weight("БВГДЖ") == pytest.approx(1.4)
    assert tu.weight("7") == pytest.approx(1.6)
    assert tu.weight("ab.") == pytest.approx(1.0 + 0.28 + 1.0)
    assert tu.weight("ma,") == pytest.approx(0.28 + 1.0 + 0.6)
    # длиннее фраза — тяжелее; регистр не важен
    assert tu.weight("PEOPLE SAY") == tu.weight("people say") < tu.weight("people say it takes")


def test_ends_with_comma():
    for s in ("one,", "two: ", "three;", "four —", "five-"):
        assert tu.ends_with_comma(s), s
    for s in ("six.", "seven", "", "   "):
        assert not tu.ends_with_comma(s), s


def test_word_count():
    assert tu.word_count("It's *very* well-known | [sighs] fact, 21 times.") == 7  # It's = 2 слова

    assert tu.word_count("") == 0
    assert tu.word_count("Привет, мир!") == 2


@pytest.mark.parametrize("n, want", [(1, "habit"), (-1, "habit"), (0, "habits"), (2, "habits"), (1.0, "habit")])
def test_plural_en(n, want):
    assert plural(n, ["habit", "habits"]) == want


@pytest.mark.parametrize("n, want", [
    (1, "день"), (21, "день"), (101, "день"), (-1, "день"),
    (2, "дня"), (4, "дня"), (22, "дня"), (104, "дня"),
    (0, "дней"), (5, "дней"), (11, "дней"), (12, "дней"), (14, "дней"), (19, "дней"), (111, "дней"), (114, "дней"),
    (2.7, "дня"),  # дробь — по целой части
])
def test_plural_ru(n, want):
    assert plural(n, ["день", "дня", "дней"]) == want


def test_plural_fixed_word():
    assert plural(5, "%") == "%"
