"""Библиотека шаблонов сцен. Каждый шаблон синхронизируется с речью через биты (beats).

Контракт шаблона (чтобы Claude мог дописывать свои в projects/<slug>/templates/*.py):
    @template("name", doc="...", params={...}, beats="как используются биты", formats=("horizontal",))
    class X(Template):
        def setup(self): ...            # один раз: спрайты, кэши (дорогое — только здесь)
        def draw(self, img, t, T): ...  # каждый кадр: t — время сцены, T — глобальное
        def feed_speed(self, t): ...    # (опц.) скорость ленты px/s -> непрерывность между сценами
Полезное: self.bt(i) / self.be(i) — начало/конец бита i; self.D — длительность сцены;
self.io(t) — альфа плавного входа/выхода; self.u — масштаб (1.0 при 1080 по короткой стороне);
self.style — стиль ролика (studio/style.py: палитра self.style.pal, цвет self.style.col("accent"), пресет).
params: значение по умолчанию (тип выводится) или P(default, "описание", type=...) — validate проверяет типы;
formats — форматы кадра, под которые свёрстан шаблон (по умолчанию все). Шаблон проекта попадает в пространство
`project` (полное имя project.<name>, в сценарии — просто <name>).

Код шаблонов — пакеты studio/packs/ (core, phone, lab); этот модуль — прежний вход, имена те же (P2.4).
"""
from __future__ import annotations

from .packs import (AT, FORMATS, NUM, REGISTRY, P, Param, Template, TemplateNameError,  # noqa: F401
                    load_project_templates, plural, template)
from .packs.core.templates import Bullets, Counter, Outro, Statement, Title  # noqa: F401
from .packs.phone.feed import _PHONES, FeedStrip, PhoneTemplate, _impulse_speed, _swipes, phone_ctx  # noqa: F401
from .packs.phone.templates import Cards, PhoneClose, PhoneFeed, PhoneLock, Questions, with_alpha_img  # noqa: F401
