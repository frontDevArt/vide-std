"""Загрузка проекта-нарезки (ROADMAP B4): настройки исходника под своими, сцены-ссылки `from:` → копии сцен
исходника с контекстом строк (`_ctx`). Вызывается из `project.load`; выбор отрезков и команда — studio/cutdown.py.
Модуль не импортирует project/timing: project импортирует его (циклов в коде нет, tests/test_anim.py)."""
from __future__ import annotations

import copy
import re
from pathlib import Path

import yaml

from .config import deep_merge
from .textutil import line_jobs

# ключи project.yaml исходника, которые нарезка не наследует: у неё свои площадка, формат, главы и длительность
OWN = ("title", "topic", "chapters", "deliverables", "platform", "format", "target_duration", "cutdown",
       "schema_version")
INHERITED_PARAMS = ("chrome",)  # params, которые шаблоны lab передают через state: копим к первой сцене-ссылке
REF = re.compile(r"^(?:(?P<ch>[\w-]+)/)?(?P<sid>[\w-]+)$")


def source_root(root: Path, src: str, resolve_project) -> Path:
    """Исходник нарезки: соседняя папка в projects/ студии, иначе путь или slug (project.resolve_project)."""
    for p in (root.parent / src, Path(src)):
        if (p / "project.yaml").exists():
            return p.resolve()
    return resolve_project(src)


def read_yaml(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def inherit(src_user: dict, user: dict) -> dict:
    """project.yaml нарезки поверх project.yaml исходника (кроме OWN)."""
    base = {k: v for k, v in src_user.items() if k not in OWN}
    return deep_merge(base, user)


def source_chapters(src: Path, src_user: dict) -> list:
    """[(id, data)] глав исходника в порядке project.yaml."""
    out = []
    for ch in src_user.get("chapters") or []:
        p = src / "script" / f"{ch}.yaml"
        if p.exists():
            out.append((ch, read_yaml(p)))
    return out


def _split(ref, ch) -> tuple[str, str]:
    m = REF.match(str(ref).strip())
    if not m:
        raise SystemExit(f"{ch}: from: {ref!r} — нужно chNN/sNN или sNN")
    return m["ch"] or ch, m["sid"]


def resolve(chapters: list, src_chs: list, src_name: str) -> list:
    """Сцены-ссылки `from:` → копии сцен исходника (+ свои ключи поверх) с контекстом строк исходника."""
    index = {}
    for sch, data in src_chs:
        scenes = data.get("scenes") or []
        for i, (sc, jobs) in enumerate(zip(scenes, line_jobs(scenes))):
            index[(sch, sc.get("id"))] = (i, sc, [[prev, nxt] for _, _, prev, nxt, _ in jobs])
    order = {k: n for n, k in enumerate(index)}
    src_glow = {sch: data["glow"] for sch, data in src_chs if data.get("glow")}
    out, first_ref, first_lab = [], None, None
    for ch, data in chapters:
        data = dict(data)
        if "glow" not in data and ch in src_glow:
            data["glow"] = src_glow[ch]
        scenes = []
        for sc in data.get("scenes") or []:
            if "from" not in sc:
                scenes.append(sc)
            else:
                key = _split(sc["from"], ch)
                if key not in index:
                    raise SystemExit(f"{ch}: from: {sc['from']} — нет сцены {key[0]}/{key[1]} в {src_name}")
                _, base, ctx = index[key]
                over = {k: v for k, v in sc.items() if k != "from"}
                new = deep_merge(copy.deepcopy(base), over)
                if "lines" not in over and base.get("lines"):
                    new["_ctx"] = ctx  # кэш озвучки исходника: тот же текст, голос и соседние строки
                scenes.append(new)
                first_ref = first_ref or key
            if first_lab is None and str(scenes[-1].get("template", "")).startswith("lab"):
                first_lab = scenes[-1]
        data["scenes"] = scenes
        out.append((ch, data))
    if first_ref and first_lab is not None:  # шапка lab живёт в state: копим её к началу нарезки
        acc = {}
        for k, n in order.items():
            if n >= order[first_ref]:
                break
            p = index[k][1].get("params") or {}
            for name in INHERITED_PARAMS:
                if isinstance(p.get(name), dict):
                    acc[name] = deep_merge(acc.get(name, {}), p[name])
        if acc:
            first_lab["params"] = deep_merge(acc, first_lab.get("params") or {})
    return out
