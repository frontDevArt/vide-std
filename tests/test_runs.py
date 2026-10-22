"""P1.11 (B12): разметка `*акцент*` рядом со знаками препинания."""
import pytest

from studio import gfx


def test_comma_after_closing_star():
    assert gfx._runs("Your *time*, your choice") == [
        ("Your", False), ("time,", True), ("your", False), ("choice", False)]


def test_period_after_closing_star():
    assert gfx._runs("median *66*. Done") == [("median", False), ("66.", True), ("Done", False)]


def test_brackets_around_stars():
    assert gfx._runs("see (*word*) here") == [("see", False), ("(word)", True), ("here", False)]


def test_quote_before_opening_star():
    assert gfx._runs("“*21 days* to”") == [("“21", True), ("days", True), ("to”", False)]


# Строки, которые уже разбирались верно (фикстура gallery и fake-discounts), — разбор не меняется.
@pytest.mark.parametrize("text, expected", [
    ("Твоё *время*", [("Твоё", False), ("время", True)]),
    ("The *feed*", [("The", False), ("feed", True)]),
    ("See you *next time*", [("See", False), ("you", False), ("next", True), ("time", True)]),
    ("21 days → median *66*", [("21", False), ("days", False), ("→", False), ("median", False), ("66", True)]),
    ("Could be a *fluke*", [("Could", False), ("be", False), ("a", False), ("fluke", True)]),
    ("works on skeptics · *too absurd* can backfire",
     [("works", False), ("on", False), ("skeptics", False), ("·", False), ("too", True), ("absurd", True),
      ("can", False), ("backfire", False)]),
    ("no accents, at all.", [("no", False), ("accents,", False), ("at", False), ("all.", False)]),
    ("a*b", [("a*b", False)]),
])
def test_unchanged(text, expected):
    assert gfx._runs(text) == expected


@pytest.mark.parametrize("text", ["Your *time*, your choice", "median *66*.", "(*word*)", "“*21 days*”"])
def test_no_stars_left(text):
    assert all("*" not in w for w, _ in gfx._runs(text))
