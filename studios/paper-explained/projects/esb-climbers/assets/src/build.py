"""esb-climbers «Живая бумага» (код — nvidia-huang v2): common.css + live.css + extra.css + esb.css + тело сцены +
common.js → assets/sNN-имя.html.
python studios/paper-explained/projects/esb-climbers/assets/src/build.py [s01 s02 …]
Куски: <img data-cut="ИМЯ" data-box="W H [b]"> (KEYS), <!--@scraps-->, <!--@ransom ТЕКСТ SIZE--> (буквы по клочкам),
<!--@esb--> — небоскрёб в разрезе (холст 780×2000, этажи 86 / 102 / 104 и шпиль; для камеры data-tour),
<!--@ig ФОТО ПОДПИСЬ--> — бумажный пост Instagram пары (фото people/ig/ФОТО.jpg, подпись — `_` вместо пробела)."""
import re
import sys
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-hook", "s02": "s02-who", "s03": "s03-night", "s04": "s04-hatch", "s05": "s05-lock",
         "s06": "s06-ring", "s07": "s07-live", "s08": "s08-bodycam", "s09": "s09-charges", "s10": "s10-deal",
         "s11": "s11-withdrawn", "s12": "s12-visa", "s13": "s13-deport", "s14": "s14-war", "s15": "s15-court",
         "s16": "s16-ask", "s17": "s17-sub"}
KEYS = {"SCISSORS": "../../../brand/avatar/src/scissors.cut.png", "HAND": "../../../brand/avatar/src/hand.cut.png",
        "PLANE": "../../../brand/avatar/src/plane.cut.png"}


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


def scraps(_):
    """Второй план: обрывки газет по краям (светлые, под главным)."""
    spots = [(-40, 20, 240, 160, -7), (600, -10, 230, 180, 6), (-50, 1000, 270, 170, 5), (560, 1010, 260, 160, -4),
             (650, 520, 170, 170, 9), (-60, 560, 160, 200, -5)]
    out = []
    for i, (x, y, w, h, r) in enumerate(spots):
        lines = '<i class="h"></i>' + "".join('<i class="s"></i>' if (i + j) % 3 == 2 else "<i></i>" for j in range(h // 18))
        out.append(f'<div class="scrap" data-backdrop data-torn="all" data-depth="9" style="left: {x}px; top: {y}px; width: {w}px; height: {h}px; --r: {r}deg">{lines}</div>')
    return "".join(out)


def ransom(m):
    text, size = m.group(1).replace("_", " "), m.group(2)
    kinds, rots = "abcdabdcadbc", [-6, 4, -3, 7, -5, 3, -8, 5, -2, 6, -4, 2]
    out, k = [], 0
    for ch in text:
        if ch == " ":
            out.append('<span class="sp"></span>')
            continue
        out.append(f'<span class="{kinds[k % 12]}" style="--i: {k}; --r: {rots[k % 12]}deg; font-size: {int(size) * (1 if k % 3 else 1.1):.0f}px">{ch}</span>')
        k += 1
    return "".join(out)


def esb(m):
    """Небоскрёб в разрезе на холсте 780×2000: силуэт ступенями, окна полосами, этажи-метки, шпиль с площадкой.
    Ключевые точки (для data-tour): смотровая 86 — y 560, люк 102 — y 335, замок 104 — y 268, площадка — y 128, верх — y 40.
    <!--@esb0--> — без меток этажей (крупный зум: метки ушли бы под кнопки площадки — сцена ставит свои)."""
    p = []
    body = "M140 2000 V1700 H190 V1400 H250 V700 H290 V560 H330 V470 H350 V335 H370 V268 H410 V335 H430 V470 H450 V560 H490 V700 H530 V1400 H590 V1700 H640 V2000 Z"
    p.append(f'<path d="{body}" class="esb-body"/>')
    for x in range(268, 520, 26):
        p.append(f'<line x1="{x}" y1="720" x2="{x}" y2="1390" class="esb-win"/>')
    for x in (215, 245, 545, 565):
        p.append(f'<line x1="{x}" y1="1420" x2="{x}" y2="1690" class="esb-win"/>')
    for x in range(306, 480, 22):
        p.append(f'<line x1="{x}" y1="575" x2="{x}" y2="690" class="esb-win"/>')
    p.append('<path d="M386 268 L390 40 L394 268 Z" class="esb-mast"/>')
    p.append('<rect x="358" y="122" width="64" height="12" rx="3" class="esb-plat"/>')
    p.append('<circle cx="374" cy="140" r="6" class="esb-lamp"/><circle cx="406" cy="140" r="6" class="esb-lamp"/>')
    p.append('<line x1="0" y1="2000" x2="780" y2="2000" class="esb-ground"/>')
    marks = [(560, 495, "86", "смотровая"), (335, 435, "102", "люк"), (268, 415, "104", "замок")] if m.group(1) != "0" else []
    for y, x, n, t in marks:
        p.append(f'<line x1="{x}" y1="{y}" x2="{x + 26}" y2="{y}" class="esb-tick"/>')
        p.append(f'<text x="{x + 34}" y="{y + 14}" class="esb-n">{n}</text><text x="{x + 34}" y="{y + 40}" class="esb-t">{t}</text>')
    return '<svg class="esb" width="780" height="2000" viewBox="0 0 780 2000">' + "".join(p) + "</svg>"


def ig(m):
    photo, cap = m.group(1), m.group(2).replace("_", " ")
    return (f'<div class="igpost"><div class="ighd"><img class="iga" src="people/angela.face.png" alt=""><b>angela_nikolau</b>'
            f'<img class="igl" src="logos/instagram.svg" alt=""></div><div class="igph"><img src="people/ig/{photo}.jpg" alt=""></div>'
            f'<div class="igft"><span class="ighe">♥</span><span class="igc">{cap}</span></div></div>')


css = "\n".join((SRC / f).read_text(encoding="utf-8") for f in ("common.css", "live.css", "extra.css", "esb.css"))
js = (SRC / "common.js").read_text(encoding="utf-8")
for name, out in PAGES.items():
    if sys.argv[1:] and name not in sys.argv[1:]:
        continue
    body = (SRC / f"{name}.body.html").read_text(encoding="utf-8")
    body = re.sub(r"<!--@scraps-->", scraps, body)
    body = re.sub(r"<!--@esb(0?)-->", esb, body)
    body = re.sub(r"<!--@ig (\S+) (\S+)-->", ig, body)
    body = re.sub(r"<!--@ransom (\S+) (\d+)-->", ransom, body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{out}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{out}.html")
