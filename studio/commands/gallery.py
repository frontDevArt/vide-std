"""gallery — HTML-страница с превью каждого шаблона в каждом формате (логика — studio/gallery.py, ROADMAP C4)."""
from __future__ import annotations


def add(sp):
    q = sp.add_parser("gallery", help="галерея шаблонов: превью каждого шаблона в каждом формате → output/gallery/index.html")
    q.add_argument("--formats", help="форматы через запятую: horizontal,vertical,square,portrait (по умолчанию все)")
    q.add_argument("--out", help="папка страницы (по умолчанию output/gallery/ в корне студии)")
    q.add_argument("--workers", type=int)


def run(a):
    from ..gallery import build
    build(a.formats.split(",") if a.formats else None, a.out, a.workers)
    return 0
