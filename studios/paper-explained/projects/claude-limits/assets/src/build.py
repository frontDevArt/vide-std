"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/claude-limits/assets/src/build.py

Вырезка Kie в теле сцены: `<img data-cut="<ключ>" data-box="W H">` внутри бокса W×H (`.sticker`) — вырезка
вписывается в бокс по границам непрозрачного (у картинки 2048² большие прозрачные поля), по центру.
"""
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01.body.html": "s01-hook.html", "s02.body.html": "s02-memory.html", "s03.body.html": "s03-chain.html",
         "s04.body.html": "s04-pile.html", "s05.body.html": "s05-reading.html", "s06.body.html": "s06-graphify.html",
         "s07.body.html": "s07-ponytail.html", "s08.body.html": "s08-recipe.html"}


def cut(m):
    key, (w, h) = m.group(1), map(float, m.group(2).split())
    im = Image.open(OUT / "images" / f"{key}.cut.png")
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    s = min(w / (x1 - x0), h / (y1 - y0))
    left, top = (w - (x1 - x0) * s) / 2 - x0 * s, (h - (y1 - y0) * s) / 2 - y0 * s
    return (f'<img src="images/{key}.cut.png" alt="" style="position: absolute; left: {left:.1f}px; top: {top:.1f}px; '
            f'width: {im.width * s:.1f}px; height: {im.height * s:.1f}px">')


css = (SRC / "common.css").read_text(encoding="utf-8")
js = (SRC / "common.js").read_text(encoding="utf-8")
for src, out in PAGES.items():
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. ]+)">', cut, (SRC / src).read_text(encoding="utf-8"))
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / out).write_text(html, encoding="utf-8")
    print(OUT / out)
