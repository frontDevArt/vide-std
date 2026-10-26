"""Схема project.yaml: ключи, типы и значения по умолчанию в одном месте; версия схемы и миграция старых файлов.

Значение по умолчанию попадает в cfg, только если оно задано здесь (DEFAULTS собирается из SCHEMA). Ключ без
значения по умолчанию — «известный, необязательный»: код читает его через .get(). Неизвестный ключ не ломает
загрузку — ⚠️ с подсказкой ближайшего известного (опечатка `subtitle:` иначе молча игнорировалась бы).
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass

SCHEMA_VERSION = 1

FORMATS = {  # формат кадра → (Ш, В); прежнее место — project.FORMATS (оставлено именем)
    "vertical": (1080, 1920),
    "horizontal": (1920, 1080),
    "square": (1080, 1080),
    "portrait": (1080, 1350),  # 4:5 — лента Instagram (ROADMAP B2)
}
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
    "kind": F((str,), doc="тип ролика (studio/kinds.py, ROADMAP C1): explainer | short-hook | promo | music | slideshow | "
                          "listicle | data-story | tutorial | clip; нет — explainer"),
    "brief": F((dict,), doc="поля брифа по типу ролика: hook, product, price, cta, count, photos, data… (studio/kinds.py)"),
    "audience": F((str,), doc="для кого ролик"),
    "avoid": F((list,), doc="бриф: чего избегать — строки (чек-лист глазами) и правила {max_words_on_screen: 6}, "
                            "{words: [...]}, {numbers_without_source: true} (studio/gates.py, ROADMAP D4)"),
    "done_means": F((list,), doc="бриф: что значит готово — строки (глазами) и правила {final_hold: 1.5}, "
                                 "{logo_in_final: true}, {cta_in_final: true} (studio/gates.py)"),
    "language": F((str,), "ru", "язык озвучки и текста ролика (studio/lang.py: LANGS)"),
    "fps": F((int,), 30),
    "format": F((str,), "vertical", "vertical | horizontal | square | portrait (4:5) (project.FORMATS)"),
    "platform": F((str, NONE), doc="площадка выхода: youtube | youtube-shorts | tiktok | … (studio/platforms.py)"),
    "deliverables": F((list, NONE), doc="выходы — площадки (studio/platforms.py): один сценарий и озвучка, у каждого "
                                        "свои формат, вёрстка, рендер и QA (ROADMAP B3)"),
    "target_duration": F(NUM + (NONE,), None, "секунды, если длительность точная; null — по речи"),
    "cutdown": {"source": F((str,), doc="нарезка (ROADMAP B4): slug исходника — его настройки, сцены (from:) и озвучка")},
    "translation": {"source": F((str,), doc="перевод (ROADMAP D3): slug исходника; входы — translation.yaml"),
                    "from": F((str,), doc="язык исходника")},
    "package": {  # пакет к выходу (ROADMAP B5, studio/package.py) — вне ключа рендера
        "title": F((str,), doc="название на площадке (иначе title)"),
        "description": F((str,), doc="текст описания / подписи (иначе topic)"),
        "sources": F((list,), doc="полные ссылки на источники; в описание идут те, что процитированы в сценах"),
        "sources_format": F((str,), doc="auto | full | short: «Автор (год) ссылка»; auto — короткие, "
                                        "если полные не влезают в предел описания площадки"),
        "hashtags": F((list,), doc="хэштеги для подписи (TikTok, Reels, Shorts — до предела площадки)"),
        "cover": F((dict,), doc="обложка: {at: секунды | chNN/sNN, text: ≤ 3 слов, verdict: auto | TRUE | … | none}"),
        "by_output": F((dict,), doc="поверх для выхода: {tiktok: {title, description, hashtags, cover}}"),
    },
    "tts": {
        "backend": F((str,), "rhvoice", "rhvoice | edge | piper | elevenlabs | fake | none (без голоса, ROADMAP C1)"),
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
        "palette": F((str,), "neon", "neon | calm | lab (style.PALETTES); при brand — база кита"),
        "brand": F((str, NONE), doc="бренд-кит: папка с brand.yaml от корня студии (обычно brand), docs/BRAND.md"),
        "font": F((str,), "Inter Display"),
        "mood": F((str, NONE), doc="только lab: lab | night | ember | deep | orchid"),
        "overrides": F((dict, NONE), doc="HEX поверх настроения: glow_cool, glow_warm, accent2"),
    },
    "music": {
        "enabled": F((bool,), True), "level_db": F(NUM, -13), "duck": F((bool,), True),
        "file": F((str, NONE), doc="свой трек вместо процедурного: путь от папки проекта или имя в brand/music/ студии"),
        "by_chapter": F((dict,), doc="свой трек на главу {chNN: файл} (ROADMAP C3), стык — кроссфейд"),
        "crossfade": F(NUM, doc="кроссфейд на стыке глав, с (2.0)"),
        "sync": F((str, NONE), doc="beat | bar — склейки сцен в долю / в сильную долю трека (studio/music.py)"),
        "bpm": F(NUM, doc="темп процедурного ритм-трека при sync без file (120); подсказка детектору долей"),
        "meter": F((int,), doc="долей в такте (4): сильная доля — каждая meter-я"),
    },
    "sfx": {"enabled": F((bool,), True), "level_db": F(NUM, 0)},  # звуки появления — только у шаблонов с sfx_events
    "subtitles": {"enabled": F((bool,), True), "max_lines": F((int,), 2), "size": F((int, NONE), None),
                  "style": F((str,), doc="plate | karaoke | tiktok (крупные, по слову, выше интерфейса площадки); "
                                         "нет — из пресета палитры или бренд-кита (ROADMAP C4)")},
    "render": {"workers": F((int, NONE), None), "crf": F((int,), 18), "preset": F((str,), "medium")},
    "loudness": F(NUM, -16),
    "qa": {"safe_margin": F(NUM, 0.04)},  # поля кадра для контента сцены (доля стороны), проверка safezone
    "images": {  # картинки для сцен (ROADMAP C5, docs/IMAGES.md, studio/imagegen.py); умолчания — только при блоке
        "enabled": F((bool,), False, "true — сцены могут просить картинки (image:); false — только кодовая графика"),
        "backend": F((str,), "kie", "kie | fake (процедурные PNG, офлайн) | none — сменный, как tts.backend"),
        "model": F((str,), "nano-banana-2", "модель генерации (таблица docs/IMAGES.md); входит в ключ кэша"),
        "resolution": F((str,), "2K", "1K | 2K | 4K; входит в ключ кэша"),
        "layers": F((str, NONE), "seedream/5-flash-layer-decomposition",
                    "раскладка сцены целиком (role: scene) на базу и слои с bounding_box; null — без раскладки"),
        "cutout": F((str,), "rembg", "вырезание объекта (role: subject): rembg (локально) | kie (recraft) | none"),
        "style": F((str,), "", "суффикс ко всем промптам: стиль на весь ролик; входит в ключ кэша"),
        "reference": F((str, NONE), doc="картинка-референс стиля (путь от папки проекта): держит стиль между картинками"),
        "budget_usd": F(NUM, 3, "предел на ролик, $; выше — стоп и вопрос пользователю"),
    },
    "chapters": F((list, NONE), []),
}


# Разделы, чьи умолчания попадают в cfg, только если раздел задан (project.yaml или defaults студии): без блока — как
# раньше, cfg и ключи кэша старых проектов прежние. Умолчания раздела — section_defaults(); подставляет project.load.
OPT_IN = ("images",)


def _defaults(schema: dict, top: bool = True) -> dict:
    out = {}
    for k, f in schema.items():
        if top and k in OPT_IN:
            continue
        if isinstance(f, dict):
            if _defaults(f, False):  # раздел без значений по умолчанию (cutdown) в cfg не попадает
                out[k] = _defaults(f, False)
        elif f.default is not _MISSING and k != "schema_version":
            out[k] = f.default
    return out


DEFAULTS = _defaults(SCHEMA)


def section_defaults(name: str) -> dict:
    """Умолчания раздела из OPT_IN (images): то, что получит раздел, заданный хотя бы одним ключом."""
    return _defaults(SCHEMA[name], False)


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
