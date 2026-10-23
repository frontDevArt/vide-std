"""Текст: сегменты '|', веса для оценки длительности, ёмкость субтитров."""
import re

VOWELS = set("аеёиоуыэюяaeiouy")
CONSONANTS = set("бвгджзйклмнпрстфхцчшщbcdfghjklmnpqrstvwxz")
PAUSE_PUNCT = {",": 1.2, ":": 1.6, ";": 1.6, "—": 1.6, "-": 0.6, ".": 2.0, "!": 2.0, "?": 2.0, "…": 2.2}

DIGITS = {"0": "ноль", "1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять",
          "6": "шесть", "7": "семь", "8": "восемь", "9": "девять"}


def line_text(line) -> str:
    """Строка сценария: "текст" или {text: "текст", voice: {...}} -> текст."""
    return str(line.get("text", "")) if isinstance(line, dict) else str(line)


def line_voice(line) -> dict:
    """Переопределение голоса строки ({stability, style, speed, …}) или {}."""
    return dict(line.get("voice") or {}) if isinstance(line, dict) else {}


def segments(line: str):
    """'Каждый свайп: | смешное видео, | история.' -> ['Каждый свайп:', 'смешное видео,', 'история.']"""
    return [s.strip() for s in line.split("|") if s.strip()]


def tts_text(line: str) -> str:
    """Что отдаём синтезатору: без '|', '*' и лишних пробелов. Подсказки ударения '+' оставляем."""
    t = line.replace("|", " ").replace("*", "")
    return re.sub(r"\s+", " ", t).strip()


AUDIO_TAG = re.compile(r"\[[a-z][a-z ]*\]")  # теги эмоций eleven_v3: [sighs], [whispers] — звучат, но не видны


def display_text(s: str) -> str:
    """Что показываем в субтитрах: без разметки ударений, акцентов и тегов эмоций."""
    s = AUDIO_TAG.sub(" ", s.replace("+", "").replace("*", "").replace("|", " "))
    return re.sub(r"\s+", " ", s).strip()


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


def line_jobs(scenes):
    """Задания синтеза по сценам одной главы: [[(raw, text, prev, next, voice)]].
    prev/next — соседние строки в пределах главы (через границы сцен): ElevenLabs держит по ним интонацию.
    Граница главы контекст рвёт, чтобы правка ch02 не пересинтезировала (платно) уже готовую ch01.
    voice = scene.voice, поверх — voice строки. Сцена нарезки (ROADMAP B4) несёт `_ctx` — [[prev, next]] строк из
    исходника: ключ кэша озвучки тот же, что у исходника."""
    flat = [(si, li, l) for si, sc in enumerate(scenes) for li, l in enumerate(sc.get("lines") or [])]
    texts = [tts_text(line_text(l)) for _, _, l in flat]
    out = [[] for _ in scenes]
    for i, (si, li, l) in enumerate(flat):
        v = dict(scenes[si].get("voice") or {}, **line_voice(l))
        ctx = scenes[si].get("_ctx")
        prev, nxt = ctx[li] if ctx and li < len(ctx) else (texts[i - 1] if i else None,
                                                            texts[i + 1] if i + 1 < len(texts) else None)
        out[si].append((line_text(l), texts[i], prev, nxt, v))
    return out
