"""Пакеты шаблонов сцен (P2.4).

- `core`  — title, statement, bullets, counter, outro;
- `phone` — lock, feed, cards, questions, close (первый ролик; алиасы phone_lock, phone_feed, …);
- `lab`   — шаблоны канала Notes From The Mind (алиасы lab_*), фон и элементы пресета `lab`;
- `commerce` — ценник-бирка, чек, число с разделителями тысяч (на основе lab; P2.9);
- `media` — фото, видео, запись экрана, клип, логотип-стинг, карточка продукта (ассеты проекта; ROADMAP C2);
- `kit` — общие шаблоны для любой палитры: chart (из CSV), timeline, steps, compare, map, quote, testimonial,
  lower_third, cta_end, chapter_bumper (ROADMAP C4);
- `project` — шаблоны из projects/<slug>/templates/*.py (`load_project_templates`).

Реестр, имена и типы параметров — `registry.py`. Старый вход `studio.templates` работает.
"""
from __future__ import annotations

from .registry import AT, FORMATS, NUM, P, PROJECT, REGISTRY, Param, TemplateNameError, template  # noqa: F401
from .base import Template, plural  # noqa: F401
from . import core, phone, lab, commerce, media, kit  # noqa: E402,F401  — регистрируют встроенные шаблоны


def load_project_templates(root):
    """Подхватить шаблоны проекта из projects/<slug>/templates/*.py в пространство `project`.
    Шаблоны предыдущего загруженного проекта убираются: в процессе активен один проект."""
    import importlib.util
    from pathlib import Path
    REGISTRY.drop_namespace(PROJECT)
    d = Path(root) / "templates"
    if not d.exists():
        return
    for f in sorted(d.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"project_tpl_{f.stem}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
