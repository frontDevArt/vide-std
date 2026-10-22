"""Пакет commerce — цены и покупки для роликов о деньгах и брендов (P2.9, из fake-discounts/templates/money.py).

- elements.py — спрайты бирки и чека, цепь, `rot`, `thousands`;
- tag.py — миксин `PriceTag` (бирка на верёвочке, качание, зачёркивание, груз); receipt.py — миксин `Receipt` (чек);
- templates.py — шаблоны `commerce.price_tag` и `commerce.number`.

Построен на lab (LabTemplate, фирменные цвета), поэтому шаблоны — `formats: horizontal`, как lab.*.
"""
from . import elements, tag, receipt, templates  # noqa: F401
from .receipt import Receipt  # noqa: F401
from .tag import PriceTag  # noqa: F401
from .templates import CommerceNumber, PriceTagScene  # noqa: F401
