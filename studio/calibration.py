"""Калибровка темпа голоса: `wpm` языка из `studio/lang.py` — ориентир, реальный голос бывает быстрее на ~20 %
(ElevenLabs en ≈ 185 против 155). После `voice` замер кладётся в `build/voice_calibration.json`, `validate` берёт его.
Замер годится, пока не сменились язык, бэкенд и голос."""
from __future__ import annotations

import json

from .lang import profile
from .project import Project

TOLERANCE = 0.10  # расхождение с таблицей, после которого предупреждаем


def _path(proj: Project):
    return proj.build / "voice_calibration.json"


def _key(proj: Project) -> dict:
    t = proj.cfg["tts"]
    return {"language": proj.cfg.get("language"), "backend": t["backend"], "voice": t.get("voice")}


def calibrate(proj: Project, tl: dict) -> list[str]:
    """Записать замер темпа из timeline; вернуть предупреждения (расхождение с wpm языка > 10 %)."""
    measured = tl["wpm_speech"]
    table = profile(proj.cfg.get("language"))["wpm"]
    data = {**_key(proj), "wpm": measured, "table_wpm": table, "rate": tl.get("rate"), "words": tl.get("words")}
    proj.build.mkdir(parents=True, exist_ok=True)
    _path(proj).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    diff = measured / table - 1
    if abs(diff) <= TOLERANCE:
        return []
    sec = proj.cfg.get("target_duration") or 60
    pct = f"{'+' if diff > 0 else '−'}{abs(diff) * 100:.0f} %"
    return [f"темп голоса {measured:g} слов/мин, табличный для языка {table} ({pct}): на {sec:g} c ≈ "
            f"{sec * measured / 60:.0f} слов речи, не {sec * table / 60:.0f}. validate теперь считает по замеру"]


def wpm(proj: Project) -> tuple[float, str]:
    """(слов/мин, откуда): замер этого голоса, если есть, иначе wpm языка."""
    p = _path(proj)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if all(data.get(k) == v for k, v in _key(proj).items()) and data.get("wpm"):
            return data["wpm"], f"замер голоса {data['backend']}"
    lang = proj.cfg.get("language")
    return profile(lang)["wpm"], f"язык {lang}"
