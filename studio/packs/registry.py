"""Реестр шаблонов сцен с пространствами имён (P2.4).

Полное имя шаблона — `<пакет>.<имя>`: `core.title`, `phone.feed`, `lab.flow`, `project.fd_number`. Пакет берётся из
модуля класса: `studio.packs.<пакет>…` — встроенный пакет, всё остальное (projects/<slug>/templates/*.py) — `project`.
Старые плоские имена (`title`, `phone_feed`, `lab_flow`) — алиасы; у проектных шаблонов алиас — само имя.
Два разных шаблона с одним именем или алиасом → `TemplateNameError` (раньше второй молча перетирал первый).

Параметры шаблона типизированы: `Param(тип, значение по умолчанию, описание)`. В `params=` можно писать и просто
значения по умолчанию (как раньше) — тип выводится из значения; `validate` проверяет параметры сцен по типам.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

FORMATS = ("vertical", "horizontal", "square", "portrait")
PROJECT = "project"


class TemplateNameError(ValueError):
    """Коллизия имён шаблонов."""


@dataclass(frozen=True)
class Param:
    type: tuple = ()      # допустимые типы значения; () — любой
    default: object = None
    doc: str = ""

    def check(self, v):
        """Описание несовпадения типа или None. None в значении — «не задано», допустимо всегда."""
        if v is None or not self.type:
            return None
        ok = isinstance(v, self.type) and not (isinstance(v, bool) and bool not in self.type)
        return None if ok else f"ожидается {type_name(self.type)}, а не {type(v).__name__}"

    def __repr__(self):
        s = f"{type_name(self.type)} = {self.default!r}"
        return f"{s} — {self.doc}" if self.doc else s


NUM = (int, float)
AT = (int, float, str)  # триггер lab: бит, секунды или слово


def P(default=None, doc="", type=None):
    """Параметр шаблона; тип по умолчанию — по значению по умолчанию."""
    if type is None:
        type = infer(default)
    return Param(type if isinstance(type, tuple) else (type,), default, doc)


def infer(v):
    if v is None:
        return ()
    if isinstance(v, bool):
        return (bool,)
    if isinstance(v, (int, float)):
        return NUM
    if isinstance(v, (list, tuple)):
        return (list,)
    return (type(v),)


_NAMES = {bool: "да/нет", int: "число", float: "число", str: "строка", list: "список", dict: "словарь"}


def type_name(types):
    if not types:
        return "любое"
    return " | ".join(dict.fromkeys(_NAMES.get(t, t.__name__) for t in types))


def params_of(params):
    return {k: v if isinstance(v, Param) else P(v) for k, v in (params or {}).items()}


def namespace_of(module):
    parts = module.split(".")
    if parts[:2] == ["studio", "packs"] and len(parts) > 2:
        return parts[2]
    return PROJECT


class Registry(Mapping):
    """Имя или алиас → класс шаблона. Перебор — по всем именам; `templates()` — только полные имена."""

    def __init__(self):
        self._cls = {}    # полное имя → класс
        self._names = {}  # полное имя и алиасы → полное имя

    def __getitem__(self, name):
        return self._cls[self._names[name]]

    def __iter__(self):
        return iter(self._names)

    def __len__(self):
        return len(self._names)

    def canonical(self, name):
        return self._names.get(name)

    def templates(self):
        return dict(self._cls)

    def aliases(self, full):
        return [n for n, f in self._names.items() if f == full and n != full]

    def add(self, cls, full, aliases=()):
        old = self._cls.get(full)
        if old is not None and not _same(old, cls):
            raise TemplateNameError(f"шаблон '{full}' уже есть: {_where(old)} и {_where(cls)}")
        for a in aliases:
            f = self._names.get(a)
            if f is not None and f != full:
                raise TemplateNameError(f"имя шаблона '{a}' занято: {f} ({_where(self._cls[f])}) и {full} ({_where(cls)})")
        self._cls[full] = cls
        for n in (full, *aliases):
            self._names[n] = full

    def drop_namespace(self, ns):
        gone = {f for f in self._cls if f.split(".", 1)[0] == ns}
        for f in gone:
            del self._cls[f]
        self._names = {n: f for n, f in self._names.items() if f not in gone}


def _same(a, b):
    # тот же шаблон, загруженный заново (проектные модули исполняются при каждом load_project_templates)
    return (a.__module__, a.__qualname__) == (b.__module__, b.__qualname__)


def _where(cls):
    return f"{cls.__module__}.{cls.__qualname__}"


REGISTRY = Registry()


def template(name, doc="", params=None, beats="", formats=FORMATS, aliases=()):
    """Регистрирует шаблон: `name` — имя внутри пакета, `aliases` — старые плоские имена, `formats` — форматы кадра,
    под которые шаблон свёрстан (vertical/horizontal/square/portrait)."""
    def deco(cls):
        ns = namespace_of(cls.__module__)
        full = f"{ns}.{name}"
        al = tuple(aliases) + ((name,) if ns == PROJECT and name not in aliases else ())
        bad = set(formats) - set(FORMATS)
        if bad:
            raise ValueError(f"шаблон {full}: неизвестные форматы {sorted(bad)} (есть: {', '.join(FORMATS)})")
        cls.NAME, cls.NAMESPACE, cls.ALIASES = full, ns, al
        cls.DOC, cls.PARAMS, cls.BEATS, cls.FORMATS = doc, params_of(params), beats, tuple(formats)
        REGISTRY.add(cls, full, al)
        return cls
    return deco
