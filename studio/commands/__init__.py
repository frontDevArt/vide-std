"""Команды CLI: по модулю на команду. В модуле `add(sp)` — подкоманда и её аргументы, `run(a)` — код возврата.
Тяжёлые импорты — внутри `run`: разбор аргументов не тянет numpy/Pillow."""
from __future__ import annotations

import importlib

# порядок = порядок в `python -m studio --help`
NAMES = ("doctor", "new", "validate", "voice", "stills", "render", "assemble", "qa", "all", "status", "templates",
         "frame", "demo", "selftest")


def module(name):
    return importlib.import_module(f".{name}", __name__)


def project_parser(sp, name, help):
    """Подкоманда с необязательным позиционным `project` (slug или путь)."""
    q = sp.add_parser(name, help=help)
    q.add_argument("project", nargs="?")
    return q
