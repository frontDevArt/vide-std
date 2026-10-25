"""Где лежат данные студии: проекты, канал, брифы, радар, секреты, логи, внешние голоса (REFACTOR P2.8).

Единственное место, которое знает раскладку папок. Остальной код спрашивает `current()`, а не склеивает
`STUDIO_ROOT / "projects"`.

Мультистудия (ROADMAP A1): рабочая область = студия. `default` — корень студии (старый `projects/`, ничего не
переносится насильно), остальные — `studios/<id>/` с `studio.yaml` и той же раскладкой. `python -m studio --studio <id>`
делает студию текущей (`use`), проект по slug ищется в текущей студии, а без `--studio` — во всех (`find`).
Настройки проекта: DEFAULTS → `defaults:` из `studio.yaml` студии-владельца → `project.yaml` (studio/project.py).

Модуль без импортов из `studio` — его можно звать откуда угодно (в том числе из `project` и `tts`) без циклов.
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # корень студии (код, tests/, assets/) — не рабочая область
DEFAULT = "default"                          # студия в корне: старая раскладка
KINDS = ("youtube", "brand", "client")       # studio.yaml: kind


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
    id: str = DEFAULT

    @classmethod
    def at(cls, root, id: str = DEFAULT, tools=None) -> "Workspace":
        root = Path(root)
        return cls(root=root, projects=root / "projects", channel=root / "channel", briefs=root / "briefs",
                   research=root / "research", logs=root / "logs", env=root / ".env",
                   tools=Path(tools) if tools else root / "tools", id=id)

    @property
    def template(self) -> Path:
        """Заготовка нового проекта (`new`): своя `projects/_template` студии, иначе общая из корня."""
        own = self.projects / "_template"
        return own if own.exists() else ROOT / "projects" / "_template"

    @property
    def config(self) -> dict:
        """`studio.yaml` студии (у `default` его обычно нет — пустой словарь)."""
        f = self.root / "studio.yaml"
        if not f.exists():
            return {}
        import yaml
        return yaml.safe_load(f.read_text(encoding="utf-8")) or {}

    @property
    def name(self) -> str:
        return str(self.config.get("name") or self.id)

    def project(self, slug: str) -> Path:
        return self.projects / slug

    def is_channel(self) -> bool:
        """Рабочая область — канал Notes From The Mind (есть позиционирование)."""
        return (self.channel / "POSITIONING.md").exists()


_current = Workspace.at(ROOT)


def studio(id: str | None = None, base=None) -> Workspace:
    """Студия по id: `default` (или пусто) — корень `base`, иначе `base/studios/<id>/` (нужен `studio.yaml`).
    Внешние голоса (`tools/`) общие для всех студий."""
    base = Path(base or ROOT)
    if not id or id == DEFAULT:
        return Workspace.at(base)
    root = base / "studios" / id
    if id.startswith("_") or not (root / "studio.yaml").exists():
        known = ", ".join(w.id for w in studios(base))
        raise SystemExit(f"Студия не найдена: {id} (есть: {known}; новая — studios/<id>/studio.yaml)")
    return Workspace.at(root, id=id, tools=base / "tools")


def studios(base=None) -> list[Workspace]:
    """Все студии: `default` первой, затем `studios/<id>/` с `studio.yaml` по алфавиту (`_template` — заготовка
    `new-studio`, не студия)."""
    base = Path(base or ROOT)
    d = base / "studios"
    ids = sorted(p.name for p in d.iterdir()
                 if not p.name.startswith("_") and (p / "studio.yaml").exists()) if d.exists() else []
    return [studio(None, base)] + [studio(i, base) for i in ids]


def projects(ws: Workspace) -> list[Path]:
    """Проекты студии: папки `projects/` с `project.yaml`, без заготовки `_template`."""
    if not ws.projects.exists():
        return []
    return sorted(p for p in ws.projects.iterdir() if p.name != "_template" and (p / "project.yaml").exists())


def find(slug: str, base=None) -> list[Path]:
    """Проект по slug во всех студиях (обычно 0 или 1 путь)."""
    return [w.project(slug) for w in studios(base) if (w.project(slug) / "project.yaml").exists()]


def owner(project_root) -> Workspace:
    """Студия, которой принадлежит проект: `<студия>/projects/<slug>` — по `studio.yaml` над `projects/`
    (студия из `studios/`, проект по пути), иначе текущая рабочая область."""
    root = Path(project_root).resolve().parent.parent
    cur = current()
    if root == cur.root.resolve():
        return cur
    if (root / "studio.yaml").exists() and root.parent.name == "studios":
        return Workspace.at(root, id=root.name, tools=root.parent.parent / "tools")
    if root == ROOT.resolve():
        return Workspace.at(ROOT)
    return cur


def at_dir(root) -> Workspace:
    """Студия по её папке (контент-план `batch --plan`, ROADMAP D2): текущая, если это она; папка со `studio.yaml` —
    студия с общими внешними голосами корня; иначе рабочая область в этой папке."""
    root = Path(root).resolve()
    cur = current()
    if root == cur.root.resolve():
        return cur
    if (root / "studio.yaml").exists():
        return Workspace.at(root, id=root.name, tools=ROOT / "tools")
    return Workspace.at(root)


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
    """KEY=VALUE из `.env` рабочей области -> os.environ (не перетирая уже заданные). Пустые значения пропускаются.
    У студии из `studios/<id>/` запасной — `.env` корня (`studios/../.env`): свой ключ студии важнее общего.
    Для секретов студии в процессе, где студий несколько, — `secret()`: os.environ один на всех."""
    ws = ws or current()
    _read_env(ws.env)
    if ws.id != DEFAULT:
        _read_env(_root_env(ws))


_FROM_FILE: dict[str, str] = {}  # что load_env положил в os.environ из файлов (не настоящее окружение процесса)


def _root_env(ws: Workspace) -> Path:
    return ws.env if ws.id == DEFAULT else ws.root.parent.parent / ".env"


def _parse_env(f: Path) -> dict:
    out = {}
    if not f.exists():
        return out
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if v:
            out[k] = v
    return out


def _read_env(f: Path):
    for k, v in _parse_env(f).items():
        if k not in os.environ:
            os.environ[k] = v
            _FROM_FILE[k] = v


def secret(name: str, ws: Workspace | None = None) -> str:
    """Секрет (ключ, ID голоса) для студии (ROADMAP A3): свой `studios/<id>/.env` → окружение процесса →
    корневой `.env`; нет — пустая строка. У `default` свой `.env` и есть корневой: окружение → `.env`, как раньше.
    Значение никуда не печатать: ни в лог, ни в чат, ни в ключи кэша."""
    ws = ws or current()
    if ws.id != DEFAULT:
        v = _parse_env(ws.env).get(name)
        if v:
            return v
    v = os.environ.get(name, "").strip()
    if v and _FROM_FILE.get(name) != v:  # из load_env — это файл, а не окружение: порядок решают файлы
        return v
    return _parse_env(_root_env(ws)).get(name, "")


def secret_source(name: str, ws: Workspace | None = None) -> str:
    """Откуда `secret()` возьмёт значение: «свой .env» | «окружение» | «корневой .env» | «нет» (без значения)."""
    ws = ws or current()
    if ws.id != DEFAULT and _parse_env(ws.env).get(name):
        return "свой .env"
    v = os.environ.get(name, "").strip()
    if v and _FROM_FILE.get(name) != v:
        return "окружение"
    return "корневой .env" if _parse_env(_root_env(ws)).get(name) else "нет"
