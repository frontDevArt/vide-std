"""gta6 v3 «Vice Night» (2026-11-15): common.css + live.css + vice.css (пальмы, ход) + night.css + тело сцены +
common.js → assets/sNN-имя.html. Демо v1 «Vice-бумага» (projects/gta6-demo/) собирал прежний build.py — см. git.
python studios/paper-explained/projects/gta6/assets/src/build.py [s01 s02 …]
Куски: <!--@art sNN [k0 k1 bp]--> — арт Kie сцены sNN на весь кадр (фон, медленный наезд k0→k1, точка кадра bp);
<!--@bg ПУТЬ [k0 k1 bp]--> — то же для готовой картинки (официальный арт Rockstar, фото); <!--@palm X Y H [flip] [ЦВЕТ]-->
— тёмная пальма-силуэт (подложка, качается); <!--@crowd N COLS--> — фигурки сотрудников."""
import math
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent
ROOT = OUT.parents[4]  # корень студии (vide-std)
PAGES = {"s01": "s01-hook", "s02": "s02-heroes", "s03": "s03-templates", "s04": "s04-pocketpair", "s05": "s05-logitech",
         "s06": "s06-miami", "s07": "s07-joker", "s08": "s08-disk", "s09": "s09-nz", "s10": "s10-ask", "s11": "s11-sub"}


def kie_keys():
    """{сцена: ключ картинки Kie} — из сценария (studio.imagegen.keys), файлы — assets/images/<ключ>.png."""
    sys.path.insert(0, str(ROOT))
    from studio import imagegen
    from studio.project import load
    proj = load(OUT.parent)
    return {w.split("#")[0].split("/")[1]: k for w, _r, k in imagegen.keys(proj)}


def bg(src, rest):
    """Фон на весь кадр: [k0 k1 [bp…]] [@слово[:сдвиг]] [blur] — наезд k0→k1, точка кадра bp; @слово — фон сменяется
    на слове (раскрывается кругом поверх прежнего); blur — размытый (за карточкой с тем же артом)."""
    at = next((t[1:] for t in rest if t.startswith("@")), None)
    blur = " blur" if "blur" in rest else ""
    rest = [t for t in rest if not t.startswith("@") and t != "blur"]
    k0 = rest[0] if len(rest) > 0 else "1.14"
    k1 = rest[1] if len(rest) > 1 else "1.02"
    bp = " ".join(rest[2:]) if len(rest) > 2 else "50% 50%"
    nxt = f' class="bgart next{blur}" data-at="{at}"' if at else f' class="bgart{blur}"'
    return (f'<div{nxt} data-backdrop><i style="background-image: url({src}); --k0: {k0}; --k1: {k1}; '
            f'--bp: {bp}"></i></div>')


def art(m, keys):
    scene, rest = m.group(1), (m.group(2) or "").split()
    return bg(f"images/{keys[scene]}.png", rest)


def palm(m):
    """Пальма-силуэт: ствол дугой и 8 перистых листьев с зубчатым краем. Холст 300×600, основание — низ по центру.
    X Y — левый верх на сцене, H — высота (ширина = H/2)."""
    x, y, h = float(m.group(1)), float(m.group(2)), float(m.group(3))
    flip, color = m.group(4) == "flip", m.group(5)
    p = []
    cx, cy = 178, 190
    left, right = [], []
    for i in range(21):
        t = i / 20
        bx = 150 + (cx - 150) * t + 34 * math.sin(math.pi * t) * .9
        by = 600 + (cy - 600) * t
        w = 17 - 8 * t
        left.append((bx - w, by)), right.append((bx + w, by))
    trunk = left + right[::-1]
    p.append('<path class="tr" d="M' + " L".join(f"{a:.1f} {b:.1f}" for a, b in trunk) + ' Z"/>')
    for ang, ln, droop in [(-170, 175, 70), (-140, 160, 40), (-108, 130, 10), (-72, 135, 10), (-38, 165, 40), (-8, 180, 75),
                           (-155, 120, 80), (-25, 125, 85)]:
        a = math.radians(ang)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        top, bot = [], []
        n = 16
        for i in range(n + 1):
            t = i / n
            rx = cx + ux * ln * t
            ry = cy + uy * ln * t + droop * t * t
            w = 26 * math.sin(math.pi * min(1, t * 1.05)) * (1 - .25 * t)
            z = 10 if i % 2 else 0
            top.append((rx + nx * (w + z * .6), ry + ny * (w + z * .6)))
            bot.append((rx - nx * (w * .55 + z), ry - ny * (w * .55 + z)))
        pts = top + bot[::-1]
        p.append('<path class="fr" d="M' + " L".join(f"{a_:.1f} {b_:.1f}" for a_, b_ in pts) + ' Z"/>')
    style = f"left: {x:.0f}px; top: {y:.0f}px; width: {h / 2:.0f}px; height: {h:.0f}px" + (f"; --pc: {color}" if color else "")
    return (f'<div class="palm{" mir" if flip else ""}" data-backdrop style="{style}">'
            f'<svg width="{h / 2:.0f}" height="{h:.0f}" viewBox="0 0 300 600">' + "".join(p) + "</svg></div>")


def crowd(m):
    n = int(m.group(1))
    return "".join(f'<i style="--i: {i}"></i>' for i in range(n))


def build(pages, dst, styles, keys):
    css = "\n".join((SRC / f).read_text(encoding="utf-8") for f in styles)
    js = (SRC / "common.js").read_text(encoding="utf-8")
    dst.mkdir(parents=True, exist_ok=True)
    for name, out in pages.items():
        if picks and name not in picks:
            continue
        body = (SRC / f"{name}.body.html").read_text(encoding="utf-8")
        body = re.sub(r"<!--@art (s\d\d)((?: [^>]+?)?)-->", lambda m: art(m, keys), body)
        body = re.sub(r"<!--@bg (\S+)((?: [^>]+?)?)-->", lambda m: bg(m.group(1), (m.group(2) or "").split()), body)
        body = re.sub(r"<!--@palm (-?[\d.]+) (-?[\d.]+) ([\d.]+)(?: (flip))?(?: (#\w+))?-->", palm, body)
        body = re.sub(r"<!--@crowd (\d+) (\d+)-->", crowd, body)
        html = ("<!doctype html>\n<!-- Собрано assets/src/build.py — правьте исходники. -->\n"
                '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
                + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
        (dst / f"{out}.html").write_text(html, encoding="utf-8")
        print(dst / f"{out}.html")


picks = sys.argv[1:]
build(PAGES, OUT, ("common.css", "live.css", "vice.css", "night.css"), kie_keys())
