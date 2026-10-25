"""Язык ролика: `language` в project.yaml. Профиль задаёт голоса по умолчанию, фразу проверки TTS,
ориентир темпа и проверку «чужого алфавита» в validate.

Новый язык: добавить запись в LANGS. Неизвестный код тоже работает, но голос надо указать явно.
`ui` — надписи, которые шаблоны рисуют сами (не из params): `ui(язык, ключ)`; нет ключа у языка — из UI_EN
(ru рисует их латиницей, как было до D3: стиль lab).
"""
from __future__ import annotations

UI_EN = {  # подписи шаблонов по умолчанию (lab рисовал их так до ROADMAP D3)
    "feed": "Feed",
    "source": "SOURCE", "study": "STUDY", "evidence": "EVIDENCE", "viral_claim": "VIRAL CLAIM", "vs": "VS",
    "chapter_of": "chapter {n} of {total}", "verdict_step": "VERDICT",  # шаг шапки, который зажигает штамп
    "verdicts": {"TRUE": "TRUE", "HALF-TRUE": "HALF-TRUE", "MYTH": "MYTH", "NO EVIDENCE": "NO EVIDENCE"},
}

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
        "voices": {"rhvoice": "slt", "edge": "en-US-AndrewMultilingualNeural", "piper": "en_US-lessac-medium"},
        "foreign": r"[А-Яа-яЁё]",
        "foreign_msg": "кириллица в английском тексте",
        "ui": {"feed": "Feed"},
    },
    "es": {
        "name": "испанский",
        "wpm": 160,
        "probe": "Prueba de voz.",
        "voices": {"edge": "es-ES-AlvaroNeural", "piper": "es_ES-davefx-medium"},
        "foreign": r"[А-Яа-яЁё]",
        "foreign_msg": "кириллица в испанском тексте",
        "ui": {"feed": "Para ti", "source": "FUENTE", "study": "ESTUDIO", "evidence": "EVIDENCIA",
               "viral_claim": "AFIRMACIÓN VIRAL", "vs": "VS", "chapter_of": "capítulo {n} de {total}",
               "verdict_step": "VEREDICTO",
               "verdicts": {"TRUE": "VERDAD", "HALF-TRUE": "MEDIA VERDAD", "MYTH": "MITO",
                            "NO EVIDENCE": "SIN PRUEBAS"}},
    },
}

GENERIC = {"name": "?", "wpm": 145, "probe": "Test.", "voices": {}, "foreign": None, "foreign_msg": "",
           "ui": {"feed": "Feed"}}


def profile(code: str | None) -> dict:
    return LANGS.get((code or "ru").lower(), GENERIC)


def ui(code: str | None, key: str):
    """Надпись шаблона на языке ролика: профиль языка, иначе UI_EN."""
    return profile(code)["ui"].get(key, UI_EN[key])


def verdict_word(code: str | None, verdict: str) -> str:
    """Слово штампа вердикта на языке ролика; цвет штампа — по исходному TRUE | HALF-TRUE | MYTH | NO EVIDENCE."""
    v = str(verdict).upper()
    return ui(code, "verdicts").get(v, v)


def default_voice(code: str | None, backend: str) -> str | None:
    return profile(code)["voices"].get(backend)
