"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/voice-clone/assets/src/build.py

Вырезка в теле сцены: `<img data-cut="<ИМЯ>" data-box="W H [b]">` внутри бокса W×H — вписывается по границам
непрозрачного, по центру (с «b» — по нижнему краю). ИМЯ → путь к вырезке от папки assets/ — в keys.txt (вырезки бренда).

Лист лечения s06–s08 — общий кусок `<!--@sheet {"intro": true|false, "done": N, "add": {"3": ["слово", "слово:сдвиг"]}}-->`:
build.py ставит конверт и лист на одно и то же место во всех сценах (склейки). intro — конверт падает, клапан
открывается, лист выходит и разворачивается (s06); без intro — лист уже развёрнут. done — пунктов уже написано (с
галочкой); add — номер пункта → [слово, на котором он пишется; слово галочки]. Остальные пункты — пустые строки.
"""
import json
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-voice", "s02": "s02-code", "s03": "s03-cut", "s04": "s04-talk", "s05": "s05-copy",
         "s06": "s06-letter", "s07": "s07-you", "s08": "s08-parents", "s09": "s09-cured", "s10": "s10-share",
         "s11": "s11-follow"}
KEYS = {}
for line in (SRC / "keys.txt").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#"):
        name, key = line.split()
        KEYS[name] = key

# ── лист лечения: конверт 660×370 в (40, 470) px сцены; лист 600×230 втрое, после подъёма — 70…670 × 90…780 ──
ROWS = ["код входа — никому", "облачный пароль — включить", "просят денег — перезвонить", "кодовое слово семьи"]
FALL = "--fy: 520px; --fr: 6deg"


def tick(on, at=None):
    a = f' data-at="{at}"' if at else ""
    return (f'<svg class="tick" viewBox="0 0 60 60"><path class="draw{" on" if on else ""}" pathLength="1"{a} '
            f'style="--dd: .22s" d="M10 32 L 25 47 L 52 12"/></svg>')


def sheet(o):
    intro, done, add = o.get("intro", False), o.get("done", 0), o.get("add", {})

    def row(i):
        n, txt = i + 1, ROWS[i]
        if n <= done:
            return f'<div class="row2"><span class="cb"></span><div class="it">{txt}</div>{tick(True)}</div>'
        if str(n) in add:
            w, t = add[str(n)]
            return (f'<div class="row2"><span class="cb"></span><div class="it write" data-at="{w}" data-sfx="marker">'
                    f'{txt}</div>{tick(False, t)}</div>')
        return f'<div class="row2"><span class="cb"></span><div class="it" style="visibility: hidden">{txt}</div></div>'

    shd = (lambda d: f'<div class="shd" style="--d: {d}s"></div>') if intro else (lambda d: "")
    env = ('<div class="env drop" style="left: 40px; top: 470px; --r: 0deg; --d: .05s">' if intro
           else '<div class="env" style="left: 40px; top: 470px">')
    fold = ('<div class="fold up" style="left: 30px; top: 100px; --d: .85s">' if intro
            else '<div class="fold" style="left: 30px; top: 100px; transform: translateY(-250px)">')
    html = [env]
    if intro:
        html.append(f'<div class="env-back fall" style="--d: 1.25s; {FALL}"></div>')
    html += [fold,
             '<div class="pn mid"><div class="face"><span class="who" style="background: var(--navy)">вам</span>'
             + row(0) + row(1) + "</div></div>",
             f'<div class="pn bot{" unfoldB" if intro else ""}" style="--d: 1.9s">'
             '<div class="face" style="box-shadow: 0 12px 14px rgba(60, 45, 20, .22)">'
             '<span class="who" style="background: var(--terra-dk)">родителям</span>' + row(2) + row(3) + shd(1.9)
             + '</div><div class="back"></div></div>',
             f'<div class="pn top{" unfoldT" if intro else ""}" style="--d: 1.5s"><div class="face">'
             '<div class="hd2">Как не попасться</div>'
             '<span class="hand" style="margin-top: 12px; color: var(--terra-dk); font-size: 50px">один лист — на всю семью</span>'
             + shd(1.5) + '</div><div class="back" style="display: flex; align-items: center; justify-content: center">'
             '<span class="hand" style="font-size: 76px; transform: rotate(-4deg)">маме и папе ♥</span></div></div>',
             "</div>"]
    if intro:
        html += [f'<div class="env-pocket fall" style="--d: 1.25s; {FALL}"></div>',
                 f'<div class="pstamp fall" style="left: 540px; top: 236px; --d: 1.25s; {FALL}"></div>',
                 '<div class="flapw" style="animation: flapz .4s linear .45s both, fall .5s cubic-bezier(.5, 0, .9, .6) '
                 f'1.25s both; {FALL}"><div class="flap flapOpen" style="--d: .45s"></div></div>']
    html.append("</div>")
    return "\n".join(html)


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
    body = re.sub(r"<!--@sheet (\{.*?\})-->", lambda m: sheet(json.loads(m.group(1))), body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{name}.html")
