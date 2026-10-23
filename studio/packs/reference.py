"""Справочник шаблонов в Markdown из метаданных реестра (P5.3): `python -m studio templates --md`.

Блок между маркерами `BEGIN`/`END` в `docs/SCENE_SPEC.md` генерируется (`templates --md --write`), руками не правится —
тест `tests/test_templates_md.py` падает, если документ разошёлся с кодом.
Общие параметры базы (`COMMON` у класса, например у `LabTemplate`) не повторяются у каждого шаблона, а перечисляются
одной строкой: у шаблона показываются только его собственные.
"""
from __future__ import annotations

import re

from .registry import PROJECT, type_name

BEGIN = "<!-- templates:begin — генерируется `python -m studio templates --md --write`, руками не править -->"
END = "<!-- templates:end -->"
PACK_ORDER = ("core", "phone", "lab", "commerce", PROJECT)


def _cell(s, code=False):
    s = str(s).replace("|", "\\|").replace("\n", " ").strip()
    return s if code else s.replace("*", "\\*")  # `*слово*` в описаниях — буквально, не курсив


def _code(v):
    return f"`{_cell(repr(v), code=True)}`"


def _common(cls):
    """Имена параметров шаблона, взятые из `COMMON` базы как есть (тот же объект Param)."""
    common = getattr(cls, "COMMON", None) or {}
    return [k for k, p in cls.PARAMS.items() if common.get(k) is p]


def _pack_key(full):
    ns = full.split(".", 1)[0]
    return (PACK_ORDER.index(ns) if ns in PACK_ORDER else len(PACK_ORDER), full)


def markdown(registry, project=False):
    """Справочник: сводная таблица и по разделу на шаблон. `project=False` — только встроенные пакеты."""
    items = sorted(((n, c) for n, c in registry.templates().items()
                    if project or n.split(".", 1)[0] != PROJECT), key=lambda nc: _pack_key(nc[0]))
    out = ["| Шаблон | Алиас | Для чего | Форматы |", "|---|---|---|---|"]
    for n, c in items:
        al = ", ".join(f"`{a}`" for a in registry.aliases(n)) or "—"
        out.append(f"| [`{n}`](#{_anchor(n)}) | {al} | {_cell(_summary(c.DOC))} | {', '.join(c.FORMATS)} |")
    commons = {}
    for n, c in items:
        out += ["", f"### {n}", "", _cell(c.DOC) or "—", ""]
        if c.BEATS:
            out.append(f"- **Биты:** {_cell(c.BEATS)}")
        out.append(f"- **Форматы:** {', '.join(c.FORMATS)}")
        common = _common(c)
        if common:
            base = next(b for b in c.__mro__ if "COMMON" in vars(b))
            commons[base.__name__] = base.COMMON
            out.append(f"- **Общие параметры `{base.__name__}`:** {', '.join(f'`{k}`' for k in common)}")
        own = [(k, p) for k, p in c.PARAMS.items() if k not in common]
        if own:
            out += ["", "| Параметр | Тип | По умолчанию | Описание |", "|---|---|---|---|"]
            out += [f"| `{k}` | {_cell(type_name(p.type))} | {_code(p.default)} | {_cell(p.doc)} |" for k, p in own]
    for name, common in commons.items():
        out += ["", f"### Общие параметры `{name}`", "", "| Параметр | Тип | По умолчанию | Описание |", "|---|---|---|---|"]
        out += [f"| `{k}` | {_cell(type_name(p.type))} | {_code(p.default)} | {_cell(p.doc)} |" for k, p in common.items()]
    return "\n".join(out) + "\n"


def _summary(doc):
    """Первое предложение описания — для сводной таблицы."""
    m = re.match(r"(.+?[.!?])(\s+[A-ZА-ЯЁ«]|$)", doc or "")  # «опц. подсветка» — не конец предложения
    return m.group(1) if m else (doc or "—")


def _anchor(name):
    # якорь заголовка GitHub: нижний регистр, точки и прочая пунктуация убираются
    return re.sub(r"[^\w\- ]", "", name.lower()).replace(" ", "-")


def replace_block(text, block):
    """Подставить блок между маркерами; маркеров нет — ValueError."""
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < i:
        raise ValueError("в документе нет маркеров блока шаблонов")
    return text[:i] + BEGIN + "\n" + block + text[j:]


def block_of(text):
    i, j = text.find(BEGIN), text.find(END)
    if i < 0 or j < i:
        return None
    return text[i + len(BEGIN) + 1:j]
