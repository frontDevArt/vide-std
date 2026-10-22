"""Прежний вход пресета `lab`: код — пакет studio/packs/lab/ (P2.4), здесь те же имена, что были в lab.py.

Шаблоны проектов подменяли функции модуля (`studio.lab._li = …` в fake-discounts/templates/money.py) — запись
атрибута передаётся в модуль пакета, где имя определено, поэтому подмена по-прежнему действует.
"""
from __future__ import annotations

import sys
import types

from .packs.lab import background, base, crowd, elements, hero, templates, triggers

_PARTS = (elements, background, triggers, base, hero, crowd, templates)

for _m in _PARTS:
    globals().update({k: v for k, v in vars(_m).items() if not k.startswith("__") and k != "annotations"})


class _Compat(types.ModuleType):
    def __setattr__(self, name, value):
        for m in _PARTS:
            if name in vars(m):
                setattr(m, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _Compat
