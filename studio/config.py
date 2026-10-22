"""Схема project.yaml: ключи, типы и значения по умолчанию в одном месте; версия схемы и миграция старых файлов.

Значение по умолчанию попадает в cfg, только если оно задано здесь (DEFAULTS собирается из SCHEMA). Ключ без
значения по умолчанию — «известный, необязательный»: код читает его через .get(). Неизвестный ключ не ломает
загрузку — ⚠️ с подсказкой ближайшего известного (опечатка `subtitle:` иначе молча игнорировалась бы).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

SCHEMA_VERSION = 1
_MISSING = object()
NUM = (int, float)
NONE = type(None)


@dataclass(frozen=True)
class F:
    """Поле схемы: допустимые типы, значение по умолчанию (_MISSING — нет), описание."""
    types: tuple
    default: object = _MISSING
    doc: str = ""


SCHEMA = {
    "schema_version": F((int,), doc="версия схемы project.yaml; нет — старый файл, migrate() поднимет"),
    "title": F((str,), doc="название ролика"),
    "topic": F((str,), doc="тема"),
    "audience": F((str,), doc="для кого ролик"),
    "language": F((str,), "ru", "язык озвучки и текста ролика (studio/lang.py: LANGS)"),
    "fps": F((int,), 30),
    "format": F((str,), "vertical", "vertical | horizontal | square (project.FORMATS)"),
    "target_duration": F(NUM + (NONE,), None, "секунды, если длительность точная; null — по речи"),
    "tts": {
        "backend": F((str,), "rhvoice", "rhvoice | edge | piper | elevenlabs | fake"),
        "voice": F((str, NONE), "auto"),
        "rate": F(NUM + (str,), 105, "число или auto"),
        "rate_range": F((list,), [98, 125]),
        "model": F((str,), doc="elevenlabs: модель (иначе ELEVENLABS_MODEL_ID из .env)"),
        "context": F((bool,), doc="elevenlabs: previous_text/next_text"),
        "stability": F(NUM), "similarity_boost": F(NUM), "style": F(NUM),
        "use_speaker_boost": F((bool,)), "speed": F(NUM),
    },
    "pauses": {
        "start": F(NUM, 0.45), "comma": F(NUM, 0.18), "sentence": F(NUM, 0.40), "scene": F(NUM, 0.55),
        "end": F(NUM, 0.6), "max_extra_gap": F(NUM, 0.45),
    },
    "style": {
        "palette": F((str,), "neon", "neon | calm | lab (gfx.PALETTES)"),
        "font": F((str,), "Inter Display"),
        "mood": F((str, NONE), doc="только lab: lab | night | ember | deep | orchid"),
        "overrides": F((dict, NONE), doc="HEX поверх настроения: glow_cool, glow_warm, accent2"),
    },
    "music": {
        "enabled": F((bool,), True), "level_db": F(NUM, -13), "duck": F((bool,), True),
        "file": F((str, NONE), doc="своя музыка вместо процедурной"),
    },
    "sfx": {"enabled": F((bool,), True), "level_db": F(NUM, 0)},  # звуки появления — только у шаблонов с sfx_events
    "subtitles": {"enabled": F((bool,), True), "max_lines": F((int,), 2), "size": F((int, NONE), None)},
    "render": {"workers": F((int, NONE), None), "crf": F((int,), 18), "preset": F((str,), "medium")},
    "loudness": F(NUM, -16),
    "qa": {"safe_margin": F(NUM, 0.04)},  # поля кадра для контента сцены (доля стороны), проверка safezone
    "chapters": F((list, NONE), []),
}


def _defaults(schema: dict) -> dict:
    out = {}
    for k, f in schema.items():
        if isinstance(f, dict):
            out[k] = _defaults(f)
        elif f.default is not _MISSING and k != "schema_version":
            out[k] = f.default
    return out


DEFAULTS = _defaults(SCHEMA)


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# Миграции по версиям: MIGRATIONS[n] переводит словарь версии n в n+1. Файл без schema_version — версия 0
# (всё, что написано до P2.1): по ключам он совпадает с версией 1, миграция только ставит номер.
MIGRATIONS = {0: lambda d: d}


def migrate(user: dict) -> dict:
    """Старый project.yaml → текущая схема, в памяти (файл не трогаем)."""
    d = dict(user or {})
    v = d.get("schema_version", 0)
    if not isinstance(v, int) or v < 0:
        raise SystemExit(f"project.yaml: schema_version должен быть целым ≥ 0, а не {v!r}")
    if v > SCHEMA_VERSION:
        raise SystemExit(f"project.yaml: schema_version {v} новее студии ({SCHEMA_VERSION}) — обновите студию")
    while v < SCHEMA_VERSION:
        d = MIGRATIONS[v](d)
        v += 1
    d["schema_version"] = SCHEMA_VERSION
    return d


def _type_name(types: tuple) -> str:
    names = {int: "целое", float: "число", str: "строка", bool: "да/нет", list: "список", dict: "словарь",
             NONE: "null"}
    seen = []
    for t in types:
        n = "число" if t is int and float in types else names.get(t, t.__name__)
        if n not in seen:
            seen.append(n)
    return " | ".join(seen)


def _type_ok(v, types: tuple) -> bool:
    if isinstance(v, bool):  # bool — подкласс int: True не должен проходить за число
        return bool in types
    return isinstance(v, types)


def check(user: dict, schema: dict = SCHEMA, prefix: str = "") -> list[str]:
    """Неизвестные ключи (с подсказкой ближайшего) и значения не того типа. Только предупреждения."""
    warns = []
    for k, v in (user or {}).items():
        path = f"{prefix}{k}"
        f = schema.get(k)
        if f is None:
            near = difflib.get_close_matches(str(k), [str(x) for x in schema], n=1, cutoff=0.6)
            hint = f" — может быть, {prefix}{near[0]}?" if near else " — игнорируется"
            warns.append(f"неизвестный ключ {path}{hint}")
        elif isinstance(f, dict):
            if isinstance(v, dict):
                warns += check(v, f, path + ".")
            else:
                warns.append(f"{path} должен быть словарём, а не {v!r}")
        elif not _type_ok(v, f.types):
            warns.append(f"{path} = {v!r}: ожидается {_type_name(f.types)}")
    return warns
