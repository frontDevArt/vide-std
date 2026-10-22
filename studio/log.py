"""Логи команд из одного места: всё, что команда пишет в консоль, дублируется в файл
`projects/<slug>/logs/<команда>-<время>.log` (команды без проекта — `logs/` рабочей области, studio/workspace.py).
Консоль не меняется: поток-«тройник» отдаёт вывод в прежний `sys.stdout`/`sys.stderr` как есть."""
from __future__ import annotations

import contextlib
import sys
import time
import traceback
from pathlib import Path

from . import workspace

KEEP = 20  # сколько последних логов одной команды хранить в папке


class Tee:
    """Пишет в исходный поток и в файл; остальное (isatty, encoding, fileno) — от исходного потока."""

    def __init__(self, stream, f):
        self._stream, self._f = stream, f

    def write(self, s):
        n = self._stream.write(s)
        self._f.write(s)
        return n

    def flush(self):
        self._stream.flush()
        self._f.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def log_dir(project_root: Path | None) -> Path:
    return Path(project_root) / "logs" if project_root else workspace.current().logs


def _prune(d: Path, command: str):
    old = sorted(d.glob(f"{command}-*.log"))[:-KEEP]  # имя = время: по имени — по порядку запуска
    for p in old:
        with contextlib.suppress(OSError):
            p.unlink()


@contextlib.contextmanager
def session(command: str, project_root: Path | None = None, argv=None):
    """Дублирует stdout/stderr команды в лог; исключение пишется в лог с трассировкой и летит дальше."""
    d = log_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = d / f"{command}-{stamp}.log"
    same = sorted(d.glob(f"{command}-{stamp}*.log"))
    if same:  # несколько запусков за секунду: `_01`, `_02`… — после последнего, по имени тоже позже
        last = same[-1].stem.rpartition("_")
        path = d / f"{command}-{stamp}_{int(last[2]) + 1 if last[1] else 1:02d}.log"
    out, err = sys.stdout, sys.stderr
    with open(path, "w", encoding="utf-8", errors="replace", newline="") as f:
        f.write(f"# python -m studio {' '.join(argv or [command])}\n# {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        sys.stdout, sys.stderr = Tee(out, f), Tee(err, f)
        t0 = time.time()
        try:
            yield path
        except SystemExit as e:
            f.write(f"\n# выход: {e.code}\n")
            raise
        except BaseException:
            f.write("\n" + traceback.format_exc())
            raise
        finally:
            sys.stdout, sys.stderr = out, err
            f.write(f"# {time.time() - t0:.1f} c\n")
    _prune(d, command)
