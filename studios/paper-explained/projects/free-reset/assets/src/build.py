"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/free-reset/assets/src/build.py

Куски тела сцены (заменяются при сборке):
- `<img data-cut="<ИМЯ>" data-box="W H [b]">` — вырезка бренда внутри бокса W×H, по границам непрозрачного, по центру
  (с «b» — по нижнему краю). ИМЯ → путь к вырезке от папки assets/ — в keys.txt.
- `<!--@shot-->` — распечатка настоящего экрана Claude (assets/screen/usage@3x.png, 768×768 CSS px окна Settings → Usage,
  снято с аккаунта пользователя 2026-11-12) на фотобумаге с полями 14 px. Точка интерфейса (x, y) = (x + 14, y + 14)
  в координатах распечатки (и .tour). Координаты элементов — outline.md, «Настоящий экран».
- `<!--@ring {"box": [x0, y0, x1, y1], "at": "слово[:сдвиг]", "c": "#цвет", "w": 5, "dd": .35}-->` — кольцо маркером
  от руки вокруг бокса (рисуется на слово, звук marker).
"""
import json
import math
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-screen", "s02": "s02-bug", "s03": "s03-coupon", "s04": "s04-where", "s05": "s05-week",
         "s06": "s06-deadline", "s07": "s07-ask", "s08": "s08-follow"}
KEYS = {}
for line in (SRC / "keys.txt").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#"):
        name, key = line.split()
        KEYS[name] = key

SHOT = '<div class="shot"><img src="screen/usage@3x.png" alt=""></div>'


def ring(o):
    x0, y0, x1, y1 = o["box"]
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    seed = int(x0 * 7 + y0 * 13) % 97
    pts, n, a0 = [], 56, -2.5 + (seed % 7) * .05
    for i in range(n + 1):
        p = i / n
        a = a0 + p * 2 * math.pi * 1.12          # чуть больше оборота — конец заходит на начало
        k = 1 + .045 * math.sin(2 * a + seed) + .07 * p   # от руки: неровно и по спирали наружу
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a) + 2 * math.sin(3 * a + seed)))
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    at = f' data-at="{o["at"]}"' if o.get("at") else ""
    return (f'<svg class="ink" width="10" height="10" style="overflow: visible"><path class="draw" pathLength="1"{at} '
            f'data-sfx="marker" style="--dd: {o.get("dd", .35)}s" fill="none" stroke="{o.get("c", "#C46557")}" '
            f'stroke-width="{o.get("w", 5)}" stroke-linecap="round" stroke-linejoin="round" d="{d}"/></svg>')


def cut(m):
    name, box = m.group(1), m.group(2).split()
    src, w, h = KEYS[name], float(box[0]), float(box[1])
    im = Image.open(OUT / src)
    x0, y0, x1, y1 = im.getchannel("A").point(lambda v: 255 if v > 40 else 0).getbbox()
    s = min(w / (x1 - x0), h / (y1 - y0))
    left = (w - (x1 - x0) * s) / 2 - x0 * s
    top = h - y1 * s if box[2:] == ["b"] else (h - (y1 - y0) * s) / 2 - y0 * s
    return (f'<img src="{src}" alt="" style="position: absolute; left: {left:.1f}px; top: {top:.1f}px; '
            f'width: {im.width * s:.1f}px; height: {im.height * s:.1f}px">')


css = (SRC / "common.css").read_text(encoding="utf-8")
js = (SRC / "common.js").read_text(encoding="utf-8")
for sid, name in PAGES.items():
    src = f"{sid}.body.html"
    body = (SRC / src).read_text(encoding="utf-8")
    body = body.replace("<!--@shot-->", SHOT)
    body = re.sub(r"<!--@ring (\{.*?\})-->", lambda m: ring(json.loads(m.group(1))), body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{name}.html")
