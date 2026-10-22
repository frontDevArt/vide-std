"""Пакет lab: триггеры `at` — слово озвучки ("66", "w:median", "verdict#2"), номер бита или секунды ("1.5s").
Старт элемента — за 4 кадра до слова (STYLE §11, LabTemplate.at); trigger_errors — проверка для validate и voice (B8)."""
from __future__ import annotations

import difflib
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


def _triggers(v, path=""):
    """(путь, значение) всех триггеров: ключи `at` и `*_at` во вложенных словарях и списках."""
    if isinstance(v, dict):
        for k, x in v.items():
            p = f"{path}.{k}" if path else str(k)
            if (k == "at" or str(k).endswith("_at")) and not isinstance(x, (dict, list)):
                yield p, x
            else:
                yield from _triggers(x, p)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            yield from _triggers(x, f"{path}[{i}]")


def _near(words, spec):
    """Похожие места озвучки для подсказки: n-граммы той же длины, что триггер."""
    seq, _ = _parse_word(spec)
    k = max(1, len(seq))
    shown = [re.sub(r"^\W+|\W+$", "", str(w["w"])) for w in words]
    grams = {}
    for i in range(len(words) - k + 1):
        grams.setdefault(" ".join(_norm(w["w"]) for w in words[i:i + k]), " ".join(shown[i:i + k]))
    return [grams[g] for g in difflib.get_close_matches(" ".join(seq), list(grams), n=3, cutoff=0.6)]


def trigger_errors(scenes, registry):
    """Ненайденные триггеры `at` сцен timeline (B8): раньше — только print в процессе рендера.
    Проверяются сцены шаблонов lab (LabTemplate); слова — по той же логике, что LabTemplate.at."""
    from .base import LabTemplate  # base импортирует этот модуль
    errs = []
    for s in scenes:
        cls = registry.get(s.get("template"))
        if not (isinstance(cls, type) and issubclass(cls, LabTemplate)):
            continue
        where, words, nb = f"{s.get('chapter')}/{s.get('id')}", s.get("words") or [], len(s.get("beats") or [])
        for path, spec in _triggers(s.get("params") or {}):
            if spec is None or isinstance(spec, (bool, float)):
                continue
            if isinstance(spec, int):
                if not -nb <= spec < nb:
                    errs.append(f"{where}: {path} = {spec} — бита с таким номером нет (битов в сцене: {nb})")
                continue
            if SECONDS.fullmatch(str(spec).strip()):
                continue
            t, hits = word_time(words, spec)
            if t is not None:
                continue
            seq, occ = _parse_word(spec)
            if hits:
                errs.append(f"{where}: {path} «{spec}» — в озвучке сцены вхождений {hits}, а нужно №{occ}")
                continue
            near = _near(words, spec)
            hint = (f"похожие: {', '.join(near)}" if near else
                    "слова сцены: " + " ".join(re.sub(r"^\W+|\W+$", "", str(w["w"])) for w in words[:12])
                    + (" …" if len(words) > 12 else "")) if words else "в сцене нет озвучки"
            errs.append(f"{where}: {path} «{spec}» не найдено в озвучке; {hint}")
    return errs
