"""Голос студии (ROADMAP A3): голоса по языкам и политика акцентов из `studio.yaml`, замеры темпа — `voices.yaml`.

`studio.yaml`:
```
voices:                      # язык -> настройки tts (схема — как tts в project.yaml)
  en: {backend: elevenlabs, voice: env:ELEVENLABS_VOICE_ID, rate: 100}
  ru: {backend: piper, voice: ru_RU-ruslan-medium}
max_accents: 2               # сколько переопределений голоса (voice: сцен/строк) на ролик — без ⚠️
```
Цепочка tts проекта: DEFAULTS → `defaults:` студии → `voices[<язык проекта>]` → `project.yaml`. `voice: auto` и
`rate: auto` в project.yaml голос и темп студии не перебивают («нет своего мнения»); другой `backend` в project.yaml —
голос студии для языка не применяется целиком. `voice: env:ИМЯ` — значение из `.env` студии (`workspace.secret`):
у каждого клиента свой голос и ключ, в git и в чат они не попадают.

`voices.yaml` рядом со `studio.yaml` пишет `voice` (studio/calibration.py): измеренные слов/мин по
(язык, бэкенд, голос); голос — хэшем, не ID. `validate` нового проекта студии считает по замеру, а не по таблице языка.
"""
from __future__ import annotations

import datetime
import hashlib

from . import workspace

MAX_ACCENTS = 2  # правило канала по умолчанию: 1–2 акцента на ролик (крючок, вердикт)
FILE = "voices.yaml"


def layer(ws: workspace.Workspace, language: str | None) -> dict:
    """Настройки tts студии для языка (копия) или {}."""
    v = (ws.config.get("voices") or {}).get(language) if language else None
    return dict(v) if isinstance(v, dict) else {}


def merge_user(vl: dict, user_tts: dict) -> tuple[dict, dict]:
    """(слой студии, tts проекта) для deep_merge: другой backend в проекте — слой целиком отбрасывается;
    `voice: auto` / `rate: auto` проекта уступают голосу и темпу студии."""
    ut = dict(user_tts or {})
    if not vl or ut.get("backend", vl.get("backend")) != vl.get("backend"):
        return {}, ut
    for k in ("voice", "rate"):
        if k in vl and ut.get(k) in (None, "auto"):
            ut.pop(k, None)
    return vl, ut


def resolve_env(value, ws: workspace.Workspace):
    """`env:ИМЯ` -> секрет студии (пусто, если не задан); остальное — как есть."""
    if isinstance(value, str) and value.startswith("env:"):
        return workspace.secret(value[4:].strip(), ws)
    return value


def max_accents(ws: workspace.Workspace) -> int:
    v = ws.config.get("max_accents")
    return v if isinstance(v, int) and v >= 0 else MAX_ACCENTS


def check(ws: workspace.Workspace) -> list[str]:
    """Замечания к `voices:` и `max_accents` в studio.yaml (для `studios`)."""
    from .config import check as check_cfg
    from .lang import LANGS
    cfg, out = ws.config, []
    vs = cfg.get("voices")
    if vs is not None and not isinstance(vs, dict):
        return [f"voices: нужен словарь язык -> tts, а не {type(vs).__name__}"]
    for lang, v in (vs or {}).items():
        if lang not in LANGS:
            out.append(f"voices.{lang}: язык не из studio/lang.py ({', '.join(LANGS)})")
        if not isinstance(v, dict):
            out.append(f"voices.{lang}: нужен словарь tts (backend, voice, rate…)")
            continue
        out += [f"voices.{lang}: {w}" for w in check_cfg({"tts": v})]
        if isinstance(v.get("voice"), str) and v["voice"].startswith("env:") and not resolve_env(v["voice"], ws):
            out.append(f"voices.{lang}: {v['voice'][4:]} не задан ни в .env студии, ни в корневом")
    if "max_accents" in cfg and not (isinstance(cfg["max_accents"], int) and cfg["max_accents"] >= 0):
        out.append(f"max_accents: {cfg['max_accents']!r} — нужно целое ≥ 0")
    return out


# ---------------------------------------------------------------- замеры темпа на студию
def voice_hash(voice) -> str:
    """ID голоса в voices.yaml — хэшем: клиентский голос не светится в git."""
    return hashlib.sha1(str(voice or "").encode("utf-8")).hexdigest()[:12]


def _key(language, backend, voice) -> dict:
    return {"language": language, "backend": backend, "voice": voice_hash(voice)}


def has_store(ws: workspace.Workspace) -> bool:
    """Замеры храним только у настоящей студии (есть studio.yaml): регресс и тесты во временных папках не пишут в корень."""
    return (ws.root / "studio.yaml").exists()


def measurements(ws: workspace.Workspace) -> list[dict]:
    f = ws.root / FILE
    if not f.exists():
        return []
    import yaml
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return [m for m in data.get("measured") or [] if isinstance(m, dict)]


def save_measurement(ws: workspace.Workspace, language, backend, voice, wpm, rate=None, words=None,
                     project=None) -> bool:
    """Обновить замер (язык, бэкенд, голос) в voices.yaml студии. fake не пишем — это не голос."""
    if backend == "fake" or not has_store(ws) or not wpm:
        return False
    import yaml
    key = _key(language, backend, voice)
    rows = [m for m in measurements(ws) if {k: m.get(k) for k in key} != key]
    rows.append({**key, "wpm": wpm, "rate": rate, "words": words, "project": project,
                 "date": datetime.date.today().isoformat()})
    rows.sort(key=lambda m: (str(m.get("language")), str(m.get("backend")), str(m.get("voice"))))
    head = ("# Замеры темпа голосов студии (ROADMAP A3) — пишет `python -m studio voice`, руками не править.\n"
            "# voice — хэш ID голоса (studio/voices.py). validate новых проектов считает слова по wpm отсюда.\n")
    (ws.root / FILE).write_text(head + yaml.safe_dump({"measured": rows}, allow_unicode=True, sort_keys=False),
                                encoding="utf-8", newline="\n")
    return True


def measured_wpm(ws: workspace.Workspace, language, backend, voice):
    """Замер темпа этого голоса в студии или None."""
    key = _key(language, backend, voice)
    for m in measurements(ws):
        if {k: m.get(k) for k in key} == key and m.get("wpm"):
            return m["wpm"]
    return None
