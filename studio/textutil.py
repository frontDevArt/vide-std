"""Текст: сегменты '|', веса для оценки длительности, ёмкость субтитров."""
import re

VOWELS = set("аеёиоуыэюяaeiouy")
CONSONANTS = set("бвгджзйклмнпрстфхцчшщbcdfghjklmnpqrstvwxz")
PAUSE_PUNCT = {",": 1.2, ":": 1.6, ";": 1.6, "—": 1.6, "-": 0.6, ".": 2.0, "!": 2.0, "?": 2.0, "…": 2.2}

DIGITS = {"0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять",
          "6": "шесть", "7": "семь", "8": "восемь", "9": "девять"}


def segments(line: str):
    """'Каждый свайп: | смешное видео, | история.' -> ['Каждый свайп:', 'смешное видео,', 'история.']"""
    return [s.strip() for s in line.split("|") if s.strip()]


def tts_text(line: str) -> str:
    """Что отдаём синтезатору: без '|', '*' и лишних пробелов. Подсказки ударения '+' оставляем."""
    t = line.replace("|", " ").replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


def display_text(s: str) -> str:
    """Что показываем в субтитрах: без разметки ударений и акцентов."""
    return re.sub(r"\s+", " ", s.replace("+", "").replace("*", "").replace("|", " ")).strip()


def weight(s: str) -> float:
    """Грубая «длительность» фразы в условных единицах: гласные ~ слоги."""
    s = s.lower()
    w = 0.0
    for ch in s:
        if ch in VOWELS:
            w += 1.0
        elif ch in CONSONANTS:
            w += 0.28
        elif ch.isdigit():
            w += 1.6
        elif ch in PAUSE_PUNCT:
            w += PAUSE_PUNCT[ch] * 0.5
    return max(w, 0.5)


def ends_with_comma(s: str) -> bool:
    s = s.rstrip()
    return bool(s) and s[-1] in ",:;—-"


def word_count(text: str) -> int:
    return len(re.findall(r"[\w\-]+", display_text(text)))
