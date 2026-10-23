"""python -m studio <команда> [проект] — единая точка входа студии. Команды — studio/commands/<команда>.py."""
from __future__ import annotations

import argparse
import contextlib
import sys

from . import commands
from .commands.doctor import pinned_deps, pinned_mismatches  # noqa: F401 — прежние имена cli.*
from .commands.new import default_backend, slugify  # noqa: F401
from .project import STUDIO_ROOT  # noqa: F401


def __getattr__(name):
    """cli.cmd_<команда> — прежние имена функций команд."""
    if name.startswith("cmd_") and name[4:] in commands.NAMES:
        return commands.module(name[4:]).run
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m studio")
    p.add_argument("--studio", metavar="ID", help="студия (studios/<id>/; без флага — default и поиск проекта "
                                                  "во всех студиях): python -m studio studios")
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in commands.NAMES:
        commands.module(name).add(sp)
    a = p.parse_args(argv)
    mod = commands.module(a.cmd)
    from . import workspace
    with workspace.use(workspace.studio(a.studio)) if a.studio else contextlib.nullcontext():
        if not getattr(mod, "LOG", True):
            return _run(mod, a)
        from .log import session
        with session(a.cmd, _log_root(a), sys.argv[1:] if argv is None else argv):
            return _run(mod, a)


def _log_root(a):
    """Папка проекта для лога (projects/<slug>/logs/) или None — тогда logs/ в корне студии."""
    from .project import resolve_project
    if not hasattr(a, "project"):
        return None
    try:
        return resolve_project(a.project)
    except SystemExit:  # проекта нет — команда сама скажет об этом, лог в корень
        return None


def _run(mod, a):
    from .render import prepare_once
    from .tts import TTSUnavailable
    try:
        with prepare_once():  # P3.5: prepare() один раз на команду
            return mod.run(a)
    except TTSUnavailable as e:
        print(f"❌ Синтез речи недоступен: {e}\n"
              "Ролик без озвучки не делаем: сообщите пользователю и предложите установку (docs/TTS.md).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
