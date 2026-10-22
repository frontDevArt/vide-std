"""Пакет lab: триггеры `at` — слово озвучки ("66", "w:median", "verdict#2"), номер бита или секунды ("1.5s").
Старт элемента — за 4 кадра до слова (STYLE §11, LabTemplate.at). Проверка триггеров для validate и voice — check.py."""
from __future__ import annotations

import re


# ===================================================================== триггеры at
SECONDS = re.compile(r"([\d.]+)s")


def _norm(w):
    return re.sub(r"[^\w]+", "", str(w).lower().replace("’", "'"))


def _parse_word(spec):
    """'w:median of#2' -> (['median', 'of'], 2)."""
    s = str(spec).strip()
    s = s[2:] if s.startswith("w:") else s
    occ = 1
    if "#" in s:
        s, o = s.rsplit("#", 1)
        occ = int(o or 1)
    return [_norm(x) for x in s.split() if _norm(x)], occ


def word_time(words, spec):
    """(t0 нужного вхождения или None, сколько вхождений есть) — одна логика для рендера и проверки."""
    seq, occ = _parse_word(spec)
    ws = [_norm(w["w"]) for w in words]
    hit = 0
    for i in range(len(ws) - len(seq) + 1):
        if ws[i:i + len(seq)] == seq:
            hit += 1
            if hit == occ:
                return words[i]["t0"], hit
    return None, hit
