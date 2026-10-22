"""python -m studio <команда> [проект] — единая точка входа студии. Команды — studio/commands/<команда>.py."""
from __future__ import annotations

import argparse
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
    sp = p.add_subparsers(dest="cmd", required=True)
    for name in commands.NAMES:
        commands.module(name).add(sp)
    a = p.parse_args(argv)
    from .tts import TTSUnavailable
    try:
        return commands.module(a.cmd).run(a)
    except TTSUnavailable as e:
        print(f"❌ Синтез речи недоступен: {e}\n"
              "Ролик без озвучки не делаем: сообщите пользователю и предложите установку (docs/TTS.md).")
        return 2


if __name__ == "__main__":
    sys.exit(main())
