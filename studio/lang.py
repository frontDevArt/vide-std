"""Язык ролика: `language` в project.yaml. Профиль задаёт голоса по умолчанию, фразу проверки TTS,
ориентир темпа и проверку «чужого алфавита» в validate.

Новый язык: добавить запись в LANGS. Неизвестный код тоже работает, но голос надо указать явно.
"""
from __future__ import annotations

LANGS = {
    "ru": {
        "name": "русский",
        "wpm": 145,
        "probe": "Проверка голоса.",
        "voices": {"rhvoice": "aleksandr-hq", "edge": "ru-RU-DmitryNeural", "piper": "ru_RU-dmitri-medium"},
        "foreign": r"[A-Za-z]",
        "foreign_msg": "латиница — проверьте произношение или напишите кириллицей",
        "ui": {"feed": "Лента"},  # надписи, которые шаблоны рисуют сами (не из params)
    },
    "en": {
        "name": "английский",
        "wpm": 155,
        "probe": "Voice check.",
        "voices": {"rhvoice": "slt", "edge": "en-US-GuyNeural", "piper": "en_US-lessac-medium"},
        "foreign": r"[А-Яа-яЁё]",
        "foreign_msg": "кириллица в английском тексте",
        "ui": {"feed": "Feed"},
    },
}

GENERIC = {"name": "?", "wpm": 145, "probe": "Test.", "voices": {}, "foreign": None, "foreign_msg": "",
           "ui": {"feed": "Feed"}}


def profile(code: str | None) -> dict:
    return LANGS.get((code or "ru").lower(), GENERIC)


def default_voice(code: str | None, backend: str) -> str | None:
    return profile(code)["voices"].get(backend)
