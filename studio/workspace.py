"""Где лежат данные студии: проекты, канал, брифы, радар, секреты, логи, внешние голоса (REFACTOR P2.8).

Единственное место, которое знает раскладку папок. Остальной код спрашивает `current()`, а не склеивает
`STUDIO_ROOT / "projects"`. Пока рабочая область одна — корень студии, раскладка прежняя. Это точка входа
мультистудии (ROADMAP A1): там `current()` станет `studios/<id>/`, а код вокруг не изменится.

Модуль без импортов из `studio` — его можно звать откуда угодно (в том числе из `project` и `tts`) без циклов.
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # корень студии (код, tests/, assets/) — не рабочая область


@dataclass(frozen=True)
class Workspace:
    root: Path
    projects: Path
    channel: Path   # позиционирование, стиль, журнал тем канала
    briefs: Path
    research: Path  # радар тем
    logs: Path      # логи команд без проекта (studio/log.py)
    env: Path       # секреты: KEY=VALUE, в .gitignore
    tools: Path     # внешние голоса: rhvoice, piper-voices (tools/setup_rhvoice.sh)

    @classmethod
    def at(cls, root) -> "Workspace":
        root = Path(root)
        return cls(root=root, projects=root / "projects", channel=root / "channel", briefs=root / "briefs",
                   research=root / "research", logs=root / "logs", env=root / ".env", tools=root / "tools")

    @property
    def template(self) -> Path:
        """Заготовка нового проекта (`new`)."""
        return self.projects / "_template"

    def project(self, slug: str) -> Path:
        return self.projects / slug

    def is_channel(self) -> bool:
        """Рабочая область — канал Notes From The Mind (есть позиционирование)."""
        return (self.channel / "POSITIONING.md").exists()


_current = Workspace.at(ROOT)


def current() -> Workspace:
    return _current


@contextlib.contextmanager
def use(ws: Workspace | Path | str, **paths):
    """Временно другая рабочая область (тесты, позже — `--studio`): `use(tmp)` или `use(current(), logs=tmp)`."""
    global _current
    old = _current
    base = ws if isinstance(ws, Workspace) else Workspace.at(ws)
    _current = replace(base, **{k: Path(v) for k, v in paths.items()})
    try:
        yield _current
    finally:
        _current = old


def load_env(ws: Workspace | None = None):
    """KEY=VALUE из `.env` рабочей области -> os.environ (не перетирая уже заданные). Пустые значения пропускаются."""
    f = (ws or current()).env
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v and k not in os.environ:
            os.environ[k] = v
