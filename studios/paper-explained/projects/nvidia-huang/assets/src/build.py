"""nvidia-huang v2 «Живая бумага» (код — из утверждённого демо nvidia-huang-demo): common.css + live.css + extra.css
+ тело сцены + common.js → assets/sNN-имя.html.
python studios/paper-explained/projects/nvidia-huang/assets/src/build.py
Куски: <img data-cut="ИМЯ" data-box="W H [b]"> (KEYS), <!--@scraps-->, <!--@ransom ТЕКСТ SIZE--> (буквы по клочкам),
<!--@sil W--> — безликий бумажный силуэт (безымянных частных лиц не показываем)."""
import re
from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01": "s01-hook", "s02": "s02-nyt", "s03": "s03-letter", "s04": "s04-probe", "s05": "s05-exit",
         "s06": "s06-years", "s07": "s07-kress", "s08": "s08-market", "s09": "s09-chips", "s10": "s10-face",
         "s11": "s11-orders", "s12": "s12-rivals", "s13": "s13-cheaper", "s14": "s14-next", "s15": "s15-save"}
KEYS = {"SCISSORS": "../../../brand/avatar/src/scissors.cut.png", "HAND": "../../../brand/avatar/src/hand.cut.png",
        "CHIP": "images/56813f422a195e5e.cut.png", "CHAIR": "images/751e945d2ecbb45d.cut.png"}
SIL = ('<svg class="sil" viewBox="0 0 200 240" width="{w}" height="{h}"><path d="M100 26 C60 26 46 58 48 94 C49 120 44 138 36 148 '
       'L164 148 C156 138 151 120 152 94 C154 58 140 26 100 26 Z M20 240 C22 196 50 176 84 170 L84 146 L116 146 L116 170 '
       'C150 176 178 196 180 240 Z"/></svg>')


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
    """Второй план: 5 обрывков газет по краям (светлые, под главным)."""
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


css = "\n".join((SRC / f).read_text(encoding="utf-8") for f in ("common.css", "live.css", "extra.css"))
js = (SRC / "common.js").read_text(encoding="utf-8")
import sys
for name, out in PAGES.items():
    if sys.argv[1:] and name not in sys.argv[1:]:
        continue
    body = (SRC / f"{name}.body.html").read_text(encoding="utf-8")
    body = re.sub(r"<!--@sil (\d+)-->", lambda m: SIL.format(w=m.group(1), h=round(int(m.group(1)) * 1.2)), body)
    body = re.sub(r"<!--@scraps-->", scraps, body)
    body = re.sub(r"<!--@ransom (\S+) (\d+)-->", ransom, body)
    body = re.sub(r'<img data-cut="(\w+)" data-box="([\d. b]+)">', cut, body)
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / f"{out}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{out}.html")
