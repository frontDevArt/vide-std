"""Команды CLI: по модулю на команду. В модуле `add(sp)` — подкоманда и её аргументы, `run(a)` — код возврата.
Тяжёлые импорты — внутри `run`: разбор аргументов не тянет numpy/Pillow.
Вывод команды дублируется в `projects/<slug>/logs/<команда>-<время>.log` (studio/log.py); `LOG = False` в модуле — без лога."""
from __future__ import annotations

import importlib

# порядок = порядок в `python -m studio --help`
NAMES = ("doctor", "new", "validate", "voice", "stills", "render", "assemble", "qa", "all", "status", "templates",
         "frame", "demo", "selftest", "clean", "studios", "new-studio")


def module(name):
    return importlib.import_module(f".{name.replace('-', '_')}", __name__)


def project_parser(sp, name, help):
    """Подкоманда с необязательным позиционным `project` (slug или путь)."""
    q = sp.add_parser(name, help=help)
    q.add_argument("project", nargs="?")
    return q
