"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/shared-limit/assets/src/build.py

Вырезка Kie в теле сцены: `<img data-cut="<ИМЯ>" data-box="W H [b]">` внутри бокса W×H (`.sticker`) — вырезка
вписывается в бокс по границам непрозрачного (у картинки 2048² большие прозрачные поля), по центру (с «b» — по
нижнему краю). ИМЯ → ключ кэша картинки — в keys.txt (ключи печатает `python -m studio images shared-limit`, они же
в assets.yaml) или путь к готовой вырезке бренда от папки assets/.

Лист лечения s05–s09 — общий кусок `<!--@sheet {"done": N, "add": "слово" | null}-->`: build.py ставит лист на одно и
то же место во всех сценах (склейки), N пунктов уже написаны с галочками, пункт N+1 пишется на слове add.
"""
import json
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-hook", "s02": "s02-pain", "s03": "s03-tokens", "s04": "s04-eaters", "s05": "s05-instant",
         "s06": "s06-slider", "s07": "s07-newchat", "s08": "s08-files", "s09": "s09-cured", "s10": "s10-question",
         "s11": "s11-follow"}
KEYS = {}  # ИМЯ → ключ; из keys.txt (строки «ИМЯ ключ»)
for line in (SRC / "keys.txt").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#"):
        name, key = line.split()
        KEYS[name] = key

# ── лист лечения (px сцены 780×960): одинаков во всех сценах s05–s09 ──
ROWS = [("Instant", "простое — в"),
        ("не выше нужного", "ползунок —"),
        ("новый чат", "новая задача —"),
        ("нужные файлы", "Кодексу —")]


def sheet(o):
    """done — пунктов уже написано (с галочкой); add — слово, на котором пишется пункт done+1; tick — слово галочки
    (по умолчанию add:0.75); intro — секунды, когда лист падает в кадр (первая сцена листа). Будущие пункты — номер и
    пустой квадрат: лист с первой сцены одного размера, на склейках не прыгает."""
    done, add, intro = o.get("done", 0), o.get("add"), o.get("intro")
    tick_at = o.get("tick") or (f"{add}:0.75" if add else None)
    rows = []
    for i, (key, lead) in enumerate(ROWS):
        n = i + 1
        txt = f'<span class="txt">{lead} <b>{key}</b></span>'
        if n <= done:
            row, box = f'<div class="row">', "draw on"
        elif n == done + 1 and add:
            row, box = f'<div class="row">', "draw"
            txt = f'<span class="txt write" data-at="{add}" data-sfx="marker">{lead} <b>{key}</b></span>'
        else:
            row, box = f'<div class="row">', None
            txt = f'<span class="txt" style="visibility: hidden">{lead} <b>{key}</b></span>'
        tick = ""
        if box:
            at = f' data-at="{tick_at}"' if box == "draw" else ""
            tick = (f'<svg class="tick" viewBox="0 0 60 60"><path class="{box}" pathLength="1"{at} style="--dd: .22s" '
                    f'd="M10 32 L 25 47 L 52 12"/></svg>')
        rows.append(f'{row}<span class="n">{n}</span>{txt}<span class="cb"></span>{tick}</div>')
    anim = f' drop" style="--r: -1deg; --d: {intro}s' if intro is not None else '" style="transform: rotate(-1deg)'
    return (f'<div class="abs sheetbox{anim}" data-boil=".5"><div class="shadow"><div class="sheet cure" data-torn="t" '
            f'data-depth="7"><div class="hd">Как беречь лимит</div>' + "".join(rows) + "</div></div></div>")


def cut(m):
    name, box = m.group(1), m.group(2).split()
    key, w, h = KEYS.get(name, name), float(box[0]), float(box[1])
    # ключ с «/» — путь к готовой вырезке от папки assets/ (вырезки бренда), иначе — кэш Kie
    src = key if "/" in key else f"images/{key}.cut.png"
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
    body = re.sub(r"<!--@sheet (\{.*?\})-->", lambda m: sheet(json.loads(m.group(1))), body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{name}.html")
