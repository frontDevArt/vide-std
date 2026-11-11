"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/bot-layers/assets/src/build.py

Вырезка Kie в теле сцены: `<img data-cut="<ИМЯ>" data-box="W H [b]">` внутри бокса W×H (`.sticker`) — вырезка
вписывается в бокс по границам непрозрачного, по центру (с «b» — по нижнему краю: робот стоит на коробке).
ИМЯ → ключ кэша картинки — в keys.txt (ключи печатает `python -m studio images bot-layers`, они же в assets.yaml).

Башня коробок — общий кусок: `<!--@tower {...}-->` в теле сцены, build.py ставит коробки, робота Кузю и счётчик
«СЛОЁВ: N» на одни и те же места, чтобы на склейках башня стояла одинаково. Параметры (JSON):
  kind   "patch" — кривая башня заплаток, "straight" — ровная на фундаменте;
  n      коробок (patch) или рядов с фундаментом (straight) к концу сцены;
  add    patch: слово, на котором приходит последняя коробка (робот подпрыгивает, она падает под него);
         straight: список слов — по одному на каждый добавленный ряд (ряд из пары коробок — [слово1, слово2]);
  intro  {"box": секунды, "bot": "слово"} — первая коробка/фундамент и робот появляются в этой сцене;
  wobble "слово" — башня качается (s10); fall "слово" — башня рассыпается в груду RUBBLE (s10);
  rubble true — груда стоит с начала сцены (s11);
  hd     длительность прыжка робота (по умолчанию .7 с; коробки подряд — короче);
  counter false — без счётчика; x, y, s — сдвиг основания и масштаб (две башни рядом, s17).
"""
import json
import math
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-hook", "s02": "s02-wrong", "s03": "s03-prompt", "s04": "s04-rag", "s05": "s05-mcp",
         "s06": "s06-access", "s07": "s07-guard", "s08": "s08-cache", "s09": "s09-trace", "s10": "s10-again",
         "s11": "s11-diagnosis", "s12": "s12-recipe", "s13": "s13-foundation", "s14": "s14-core",
         "s15": "s15-tools", "s16": "s16-caught", "s17": "s17-question", "s18": "s18-follow"}
KEYS = {}  # ИМЯ → ключ; из keys.txt (строки «ИМЯ ключ»)
for line in (SRC / "keys.txt").read_text(encoding="utf-8").splitlines():
    if line.strip() and not line.startswith("#"):
        name, key = line.split()
        KEYS[name] = key

# ── башня (px сцены 780×960) ──
CX, BY = 612, 940            # центр основания и пол
BOT_W, BOT_H = 150, 250      # бокс робота Кузи (вырезка ~0,56 : 1)
LR = [-2, 1.5, -1, 2, -1.5, 1, -2, 1.5]   # наклон ярлыков на коробках заплаток
# заплатки снизу вверх: ярлык, цвет ярлыка, ширина, высота, сдвиг центра, наклон, скотч ("l"/"r"/"")
PATCH = [("МОДЕЛЬ", "navy", 270, 64, 0, 0, ""),
         ("ПРОМПТ", "mustard", 240, 58, -6, -2, "r"),
         ("RAG", "blue", 280, 70, 8, 2.5, "l"),
         ("MCP", "terra", 230, 60, -14, -3, "r"),
         ("ДОСТУП", "navy", 260, 64, -4, 2, "l"),
         ("ЗАЩИТА", "olive", 222, 56, -24, -4, "r"),
         ("КЭШ · РОУТЕР", "blue", 270, 66, -12, 3, "l"),
         ("ТРЕЙСЫ · ЭВАЛЫ", "olive", 248, 60, -36, -5, "r")]
# груда после падения (s10 → s11): центр и наклон каждой коробки, потом робота
RUBBLE = [(612, 908, 0), (380, 914, -6), (628, 842, 8), (190, 905, 18), (430, 852, -14), (720, 772, 78),
          (522, 786, -22), (300, 822, 32)]
RUBBLE_BOT = (140, 836, -80)
# лечение: ряды над фундаментом снизу вверх; ряд — коробки (ярлык, цвет, ширина)
ROWS = [[("МОДЕЛЬ", "navy", 270)], [("ПРОМПТ", "mustard", 270)], [("RAG", "blue", 270)],
        [("MCP", "terra", 126), ("ДОСТУП", "navy", 126)], [("ЗАЩИТА", "olive", 270)], [("КЭШ · РОУТЕР", "blue", 270)]]
FOUND_W, FOUND_H, ROW_H = 330, 84, 62


def patch_geo():
    y, g = BY, []
    for i, (lab, c, w, h, dx, r, tape) in enumerate(PATCH):
        y -= h
        g.append(dict(lab=lab, c=c, w=w, h=h, x=CX + dx - w / 2, y=y, r=r, tape=tape, lr=LR[i],
                      cx=CX + dx, cy=y + h / 2))
    return g


def straight_geo():
    y = BY - FOUND_H
    rows = [[dict(lab="ЭВАЛЫ · ТРЕЙСЫ", found=True, w=FOUND_W, h=FOUND_H, x=CX - FOUND_W / 2, y=y, r=0)]]
    for row in ROWS:
        y -= ROW_H
        xs = [CX - row[0][2] / 2] if len(row) == 1 else [CX - row[0][2] - 9, CX + 9]
        rows.append([dict(lab=lab, c=c, w=w, h=ROW_H, x=x, y=y, r=0, half=len(row) > 1)
                     for (lab, c, w), x in zip(row, xs)])
    return rows


def bot_patch(n):
    b = patch_geo()[n - 1]
    return b["cx"] - BOT_W / 2, b["y"] - BOT_H + 8, round(b["r"] * .6, 2)


def bot_straight(nrows):
    return CX - BOT_W / 2, straight_geo()[nrows - 1][0]["y"] - BOT_H + 8, 0.0


def at(word):
    return f' data-at="{word}"' if word else ""


def box_html(b, cls="", word=None, style=""):
    st = (f'left: {b["x"]:.1f}px; top: {b["y"]:.1f}px; width: {b["w"]}px; height: {b["h"]}px; '
          f'--r: {b.get("r", 0)}deg; {style}')
    if b.get("found"):
        inner = f'<div class="found"><b>{b["lab"]}</b><small>evals · traces</small></div>'
    else:
        tape = ""
        if b.get("tape"):
            side = "left: 26px" if b["tape"] == "l" else "right: 26px"
            rot = -7 if b["tape"] == "l" else 8
            tape = f'<div class="tape" style="{side}; top: {b["h"] - 24}px; transform: rotate({rot}deg)"></div>'
        half = " half" if b.get("half") else ""
        inner = (f'<div class="box{half}"><span class="lab" style="--c: var(--{b["c"]}); --lr: {b.get("lr", 0)}deg">'
                 f'{b["lab"]}</span>{tape}</div>')
    return f'<div class="bx shadow {cls}" style="{st}"{at(word)}>{inner}</div>'


def bot_html(pos, hops=(), cls="", word=None, style=""):
    """pos — (left, top, наклон) в начале сцены; hops — [(куда (left, top, наклон), слово, длительность)]."""
    left, top, rot = pos
    inner = f'<div class="sticker" style="position: absolute; inset: 0"><img data-cut="ROBOT" data-box="{BOT_W} {BOT_H} b"></div>'
    # каждый прыжок — вложенная обёртка; сдвиг пересчитан в её повёрнутые оси, чтобы робот встал ровно туда же,
    # где его поставит статично следующая сцена
    layers, cur, rot_acc = [], (left, top, rot), rot
    for (dst, word_, hd) in hops:
        dx, dy = dst[0] - cur[0], dst[1] - cur[1]
        a = math.radians(-rot_acc)
        lx, ly = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
        hr = dst[2] - rot_acc
        layers.append(f'--hx: {lx:.1f}px; --hy: {ly:.1f}px; --hr: {hr:.2f}deg; --hd: {hd}s" data-at="{word_}')
        cur, rot_acc = dst, dst[2]
    for st in reversed(layers):
        inner = f'<div class="hop" style="{st}">{inner}</div>'
    return (f'<div class="bx {cls}" style="left: {left:.1f}px; top: {top:.1f}px; width: {BOT_W}px; height: {BOT_H}px; '
            f'--r: {rot}deg; {style}"{at(word)} data-boil=".6">{inner}</div>')


def counter_html(start, steps, intro=None):
    """«СЛОЁВ: N»: start — цифра в начале сцены; steps — [(цифра, слово)]; intro — секунды въезда (первая сцена башни)."""
    vals = [(start, None)] + list(steps)
    digits = []
    for k, (v, word) in enumerate(vals):
        nxt = vals[k + 1][1] if k + 1 < len(vals) else None
        inner = f'<b class="pop"{at(word)}>{v}</b>' if word else f"<b>{v}</b>"
        digits.append(f'<i class="gone"{at(nxt)}>{inner}</i>' if nxt else f"<i>{inner}</i>")
    cls, st = ("kicker cnt in", f"--d: {intro}s") if intro is not None else ("kicker cnt", "")
    return f'<div class="{cls}" style="left: 0; top: 0; {st}">Слоёв: <span class="cn">{"".join(digits)}</span></div>'


def tower(o):
    kind, n = o["kind"], o["n"]
    intro, hd = o.get("intro"), o.get("hd", .7)
    parts, steps = [], []
    if kind == "patch":
        g = patch_geo()
        add = o.get("add")
        fall, rubble = o.get("fall"), o.get("rubble")
        for i, b in enumerate(g[:n]):
            if rubble:
                rx, ry, rr = RUBBLE[i]
                parts.append(box_html(dict(b, x=rx - b["w"] / 2, y=ry - b["h"] / 2, r=rr)))
            elif fall:
                rx, ry, rr = RUBBLE[i]
                sfx = ' data-sfx="paper"' if i in (7, 4, 1) else ' data-sfx="none"'
                parts.append(box_html(b, "fall", f"{fall}:{(7 - i) * .06:.2f}",
                                      f"--fx: {rx - b['cx']:.1f}px; --fy: {ry - b['cy']:.1f}px; --fr: {rr}deg").replace(
                                          "><div", f"{sfx}><div", 1))
            elif add and i == n - 1:
                parts.append(box_html(b, "drop", f"{add}:0.14"))
            elif intro and i == 0:
                parts.append(box_html(b, "drop", style=f"--d: {intro['box']}s"))
            else:
                parts.append(box_html(b))
        if o.get("bot", True):
            if rubble:
                rx, ry, rr = RUBBLE_BOT
                parts.append(bot_html((rx - BOT_W / 2, ry - BOT_H / 2, rr)))
            elif fall:
                l, t, r = bot_patch(n)
                rx, ry, rr = RUBBLE_BOT
                parts.append(bot_html((l, t, r), cls="fall", word=f"{fall}:-0.04",
                                      style=f"--fx: {rx - l - BOT_W / 2:.1f}px; --fy: {ry - t - BOT_H / 2:.1f}px; --fr: {rr}deg"))
            elif add:
                parts.append(bot_html(bot_patch(n - 1), [(bot_patch(n), add, hd)]))
            elif intro:
                parts.append(bot_html(bot_patch(n), cls="drop", word=intro["bot"]))
            else:
                parts.append(bot_html(bot_patch(n)))
        start = n - 1 if add else n
        if add:
            steps = [(n, f"{add}:0.5")]
    else:  # straight
        rows = straight_geo()
        add = o.get("add") or []
        first_new = n - len(add)
        # линейка справа — «по линейке»
        ticks = "".join(f'<path d="M{CX + 170} {y} L {CX + 170 + (12 if k % 2 else 7)} {y}"/>'
                        for k, y in enumerate(range(BY, 440, -31)))
        parts.append(f'<svg class="ink rings" width="780" height="960"><g stroke="#5B7684" stroke-width="2" opacity=".8">'
                     f'<path d="M{CX + 170} {BY} L {CX + 170} 440"/>{ticks}</g></svg>')
        hops, count, bot_from = [], 0, None
        for r_i, row in enumerate(rows[:n]):
            words = None
            if r_i >= first_new:
                w = add[r_i - first_new]
                words = w if isinstance(w, list) else [w] * len(row)
            for k, b in enumerate(row):
                count += 1
                if words:
                    parts.append(box_html(b, "drop", f"{words[k]}:0.14"))
                    steps.append((count, f"{words[k]}:0.5"))
                elif intro and r_i == 0:
                    parts.append(box_html(b, "drop", style=f"--d: {intro['box']}s"))
                else:
                    parts.append(box_html(b))
            if words:
                hops.append((bot_straight(r_i + 1), words[0], hd))
            if len(row) == 2:  # замок между MCP и ДОСТУПОМ
                lk = f"left: {CX - 34}px; top: {b['y'] - 6}px; width: 68px; height: 80px; --r: -4deg"
                if words:
                    parts.append(f'<div class="abs sticker pop" style="{lk}"{at(words[1] + ":0.3")}>'
                                 f'<img data-cut="PADLOCK" data-box="68 80"></div>')
                else:
                    parts.append(f'<div class="abs sticker" style="{lk}; transform: rotate(var(--r))">'
                                 f'<img data-cut="PADLOCK" data-box="68 80"></div>')
        start = count - len(steps)
        if o.get("bot", True):
            if hops:
                parts.append(bot_html(bot_straight(first_new), hops))
            elif intro:
                parts.append(bot_html(bot_straight(n), cls="drop", word=intro["bot"]))
            else:
                parts.append(bot_html(bot_straight(n)))
    tf = ""
    if "x" in o or "y" in o or "s" in o:
        tf = f' style="transform: translate({o.get("x", 0)}px, {o.get("y", 0)}px) scale({o.get("s", 1)})"'
    wob = ""
    if o.get("wobble"):
        tf, wob = ' style="--dd: 1.7s"', " wob"
    floor = ('<svg class="ink rings" width="780" height="960"><path class="thin" d="M300 941 L 780 941"/></svg>'
             if o.get("floor", True) else "")
    html = f'<div class="tower{wob}"{tf}{at(o["wobble"]) if o.get("wobble") else ""}>{floor}' + "".join(parts) + "</div>"
    if o.get("counter", True):
        html = counter_html(start, steps, intro["box"] if intro else None) + html
    return html


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
    body = re.sub(r"<!--@tower (\{.*?\})-->", lambda m: tower(json.loads(m.group(1))), body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{name}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{name}.html")
