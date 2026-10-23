"""Хэш кода, который рисует кадр, — для ключа кэша рендера (P2.5).

Списка файлов нет: зависимости ищутся по импортам (`ast`, вместе с ленивыми внутри функций) от корня — файла
модуля — по файлам `studio/` и `projects/<slug>/templates/`. Ключ сцены = общая часть (`render.py` и то, что он
импортирует для рисования: gfx, style, subs, фон) + замыкание модуля её шаблона + проектные шаблоны (они могут
подменять функции пакетов: `studio.lab._li = …`). Правка файла пакета делает устаревшими
сцены шаблонов, которые его импортируют, и только их.
"""
from __future__ import annotations

import ast
import functools
import hashlib
import sys
from pathlib import Path

from .project import STUDIO_ROOT

STUDIO = STUDIO_ROOT / "studio"
# из render.py не идём: подготовка данных (их результат уже в хэше сцены) и реестр пакетов (`packs/__init__`
# грузит все пакеты; код шаблона считается по сцене); профили площадок — данные: поля сетки вёрстки (B2) в ключе сцены
_NOT_DRAWING = {"studio.project", "studio.timing", "studio.packs", "studio.platforms"}


def _module_file(name):
    """studio.x.y → файл модуля (x/y.py или x/y/__init__.py) или None, если не модуль студии."""
    parts = name.split(".")
    if parts[0] != "studio":
        return None
    p = STUDIO.joinpath(*parts[1:])
    for f in (p.with_suffix(".py"), p / "__init__.py"):
        if f.is_file():
            return f
    return None


def _module_name(f):
    rel = Path(f).resolve().relative_to(STUDIO.resolve()).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(["studio"] + parts)


@functools.lru_cache(maxsize=None)
def _imports(f, mtime_ns):
    """Модули студии, которые импортирует файл f: имена `studio.*`."""
    f = Path(f)
    tree = ast.parse(f.read_bytes(), filename=str(f))
    inside = f.resolve().is_relative_to(STUDIO.resolve())
    pkg = _module_name(f).split(".") if inside else []
    if inside and f.name != "__init__.py":
        pkg = pkg[:-1]
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if not inside:
                    continue  # относительный импорт вне студии нам не интересен
                base = pkg[:len(pkg) - node.level + 1] + (node.module.split(".") if node.module else [])
            else:
                base = node.module.split(".")
            mod = ".".join(base)
            for a in node.names:  # `from . import gfx` — это модуль, а не имя из __init__
                sub = f"{mod}.{a.name}"
                out.add(sub if _module_file(sub) else mod)
    return frozenset(n for n in out if _module_file(n))


def deps(roots, skip=()):
    """Файлы студии, достижимые по импортам из roots (файлов), сами roots включительно."""
    seen, todo = set(), [Path(r).resolve() for r in roots]
    while todo:
        f = todo.pop()
        if f in seen:
            continue
        seen.add(f)
        for n in _imports(str(f), f.stat().st_mtime_ns):
            if n not in skip:
                todo.append(_module_file(n).resolve())
    return seen


def _read(f):
    return f.read_bytes()


def _digest(files):
    h = hashlib.sha1(b"render")
    for f in sorted(files, key=lambda p: p.as_posix()):
        h.update(_read(f))
    return h.hexdigest()[:10]


def project_files(proj_root):
    d = Path(proj_root) / "templates" if proj_root else None
    return sorted(d.glob("*.py")) if d and d.exists() else []


def base_files(proj_root=None):
    """Общее для всех сцен: render.py с тем, что он рисует, и проектные шаблоны с их импортами."""
    return deps([STUDIO / "render.py"], skip=_NOT_DRAWING) | deps(project_files(proj_root))


def template_file(cls):
    """Файл модуля шаблона в студии или None (проектный шаблон уже в общей части)."""
    mod = sys.modules.get(cls.__module__)
    f = getattr(mod, "__file__", None)
    return Path(f) if f and _module_file(cls.__module__) else None


def _inits(f):
    """`__init__.py` пакетов над файлом: Python исполняет их при импорте (их импорты не обходим —
    `packs/__init__` грузит все пакеты)."""
    return {d / "__init__.py" for d in Path(f).resolve().parents
            if d.is_relative_to(STUDIO.resolve()) and d != STUDIO.resolve() and (d / "__init__.py").is_file()}


def scene_code_hash(cls, proj_root=None):
    tf = template_file(cls)
    return _digest(base_files(proj_root) | (deps([tf]) | _inits(tf) if tf else set()))


def code_hash(proj_root=None):
    """Весь код, который может рисовать кадры проекта: общая часть + все пакеты."""
    return _digest(base_files(proj_root) | {f.resolve() for f in (STUDIO / "packs").rglob("*.py")})
