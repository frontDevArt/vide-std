"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/skills-gemini-codex/assets/src/build.py

Вырезка Kie в теле сцены: `<img data-cut="<ИМЯ>" data-box="W H">` внутри бокса W×H (`.sticker`) — вырезка
вписывается в бокс по границам непрозрачного (у картинки 2048² большие прозрачные поля), по центру.
ИМЯ → ключ кэша картинки — в KEYS (ключи печатает `python -m studio images skills-gemini-codex`, они же в assets.yaml).
"""
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01.body.html": "s01-hook.html", "s02.body.html": "s02-pain.html", "s03.body.html": "s03-moving.html",
         "s04.body.html": "s04-model.html", "s05.body.html": "s05-standard.html", "s06.body.html": "s06-three.html",
         "s07.body.html": "s07-argon.html", "s08.body.html": "s08-codex.html", "s09.body.html": "s09-graphify.html",
         "s10.body.html": "s10-ponytail.html", "s11.body.html": "s11-yes.html",
         "s12.body.html": "s12-follow.html"}
KEYS = {}  # ИМЯ → ключ; заполняется ниже из keys.txt (строки «ИМЯ ключ»)
for line in (SRC / "keys.txt").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#"):
        name, key = line.split()
        KEYS[name] = key


def cut(m):
    key, (w, h) = KEYS.get(m.group(1), m.group(1)), map(float, m.group(2).split())
    # ключ с «/» — путь к готовой вырезке от папки assets/ (вырезки бренда, например рука аватара), иначе — кэш Kie
    src = key if "/" in key else f"images/{key}.cut.png"
    im = Image.open(OUT / src)
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    s = min(w / (x1 - x0), h / (y1 - y0))
    left, top = (w - (x1 - x0) * s) / 2 - x0 * s, (h - (y1 - y0) * s) / 2 - y0 * s
    return (f'<img src="{src}" alt="" style="position: absolute; left: {left:.1f}px; top: {top:.1f}px; '
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
