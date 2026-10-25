"""Команды CLI: по модулю на команду. В модуле `add(sp)` — подкоманда и её аргументы, `run(a)` — код возврата.
Тяжёлые импорты — внутри `run`: разбор аргументов не тянет numpy/Pillow.
Вывод команды дублируется в `projects/<slug>/logs/<команда>-<время>.log` (studio/log.py); `LOG = False` в модуле — без лога."""
from __future__ import annotations

import importlib

# порядок = порядок в `python -m studio --help`
NAMES = ("doctor", "new", "validate", "images", "voice", "stills", "render", "assemble", "qa", "all", "status",
         "templates", "frame", "demo", "selftest", "clean", "studios", "new-studio",
         "platforms", "cutdown", "package", "kinds", "gallery", "review", "batch", "jobs", "translate")


def module(name):
    return importlib.import_module(f".{name.replace('-', '_')}", __name__)


def project_parser(sp, name, help):
    """Подкоманда с необязательным позиционным `project` (slug или путь)."""
    q = sp.add_parser(name, help=help)
    q.add_argument("project", nargs="?")
    return q


def add_out(q):
    """`--out <выход>` — один выход из deliverables проекта (ROADMAP B3); без флага — все выходы."""
    q.add_argument("--out", metavar="ВЫХОД", help="один выход из deliverables (площадка); без флага — все")


def each_out(proj, out):
    """Выходы для команды с заголовком «== выход … ==», когда их несколько."""
    outs = proj.targets(out)
    for o in outs:
        if len(outs) > 1:
            print(f"== выход {o.out}: {o.cfg['format']} {o.size[0]}×{o.size[1]} ==")
        yield o
