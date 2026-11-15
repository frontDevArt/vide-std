"""voyager-love «Золотая пластинка» (2026-11-15): common.css + live.css + gold.css + тело сцены + common.js →
assets/sNN-имя.html.  python studios/paper-explained/projects/voyager-love/assets/src/build.py [s01 s02 …]
Куски тела сцены:
<!--@art sNN [k0 k1 bp…] [@слово[:сдвиг]] [dark|warm]--> — арт Kie сцены sNN на весь кадр (наезд k0→k1, точка bp);
<!--@bg ПУТЬ [то же]--> — готовая картинка (фото NASA) на весь кадр;
<!--@flip sNN [@слово[:сдвиг]]--> — ожившая лента сцены sNN (assets/video/sNN/*.jpg, 24 к/с) на весь кадр; нет кадров —
    вместо неё арт сцены (чтобы раскладка была видна до оплаты клипов);
<!--@eeg X Y W H СИД [@слово[:сдвиг]] [ДЛИТ] [heart] [t]--> — золотая линия ЭЭГ (heart — в середине удар сердца)."""
import math
import random
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent
PROJ = OUT.parent
ROOT = PROJ.parents[3]  # корень студии (vide-std)
PAGES = {"s01": "s01-hook", "s02": "s02-lightday", "s03": "s03-hello", "s04": "s04-launch", "s05": "s05-hello55",
         "s06": "s06-call", "s07": "s07-eeg", "s08": "s08-dot", "s09": "s09-fade", "s10": "s10-love",
         "s11": "s11-send", "s12": "s12-sub"}


def kie_keys():
    """{сцена: ключ картинки Kie} — из сценария (studio.imagegen.keys), файлы — assets/images/<ключ>.png."""
    sys.path.insert(0, str(ROOT))
    from studio import imagegen
    from studio.project import load
    proj = load(PROJ)
    return {w.split("#")[0].split("/")[1]: k for w, _r, k in imagegen.keys(proj)}


def opts(rest):
    at = next((t[1:] for t in rest if t.startswith("@")), None)
    flags = [t for t in rest if t in ("dark", "warm", "blur")]
    rest = [t for t in rest if not t.startswith("@") and t not in flags]
    return at, flags, rest


def bg(src, rest):
    at, flags, rest = opts(rest)
    k0 = rest[0] if len(rest) > 0 else "1.12"
    k1 = rest[1] if len(rest) > 1 else "1.02"
    bp = " ".join(rest[2:]) if len(rest) > 2 else "50% 50%"
    cls = " ".join(["bgart"] + (["next"] if at else []) + flags)
    da = f' data-at="{at}"' if at else ""
    return (f'<div class="{cls}"{da} data-backdrop><i style="background-image: url({src}); --k0: {k0}; --k1: {k1}; '
            f'--bp: {bp}"></i></div>')


def art(m, keys):
    return bg(f"images/{keys[m.group(1)]}.png", (m.group(2) or "").split())


def flip(m, keys):
    scene, rest = m.group(1), (m.group(2) or "").split()
    at, flags, _ = opts(rest)
    frames = sorted((OUT / "video" / scene).glob("*.jpg"))
    if not frames:
        return bg(f"images/{keys[scene]}.png", rest)  # клипа ещё нет — арт сцены
    da = f' data-at="{at}"' if at else ""
    cls = "bgflip next" if at else "bgflip"
    return (f'<div class="{cls}"{da} data-backdrop><div class="flip" data-src="video/{scene}/" data-n="{len(frames)}" '
            f'data-fps="24"></div></div>')  # --d наследуется от .bgflip (data-at)


def eeg(m):
    """Линия ЭЭГ: шум из синусов разной частоты, в середине (heart) — удар сердца ЭКГ."""
    x, y, w, h, seed = (float(m.group(i)) for i in range(1, 6))
    rest = (m.group(6) or "").split()
    at = next((t[1:] for t in rest if t.startswith("@")), None)
    dd = next((t for t in rest if re.fullmatch(r"[\d.]+s", t)), "1.2s")
    heart, teal = "heart" in rest, "t" in rest
    r = random.Random(int(seed))
    fr = [(r.uniform(.02, .05), r.uniform(0, 6)), (r.uniform(.08, .14), r.uniform(0, 6)), (r.uniform(.2, .32), r.uniform(0, 6))]
    pts = []
    n = int(w / 4)
    for i in range(n + 1):
        px = i * w / n
        v = sum(a * math.sin(px * f + ph) for (f, ph), a in zip(fr, (.45, .35, .2)))
        v *= .5 + .5 * math.sin(math.pi * i / n)  # к краям тише
        u = px / w - .5
        if heart and abs(u) < .06:  # QRS: вниз — высокий пик вверх — глубоко вниз
            k = (u + .06) / .12
            v = -1.6 * math.sin(math.pi * k * 2) * math.exp(-((k - .5) ** 2) * 6) * (1 if k < .5 else 1.3)
        pts.append((px, h / 2 - v * h / 2))
    d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
    da = f' data-at="{at}"' if at else ""
    return (f'<svg class="ink" style="left: {x:.0f}px; top: {y:.0f}px" width="{w:.0f}" height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">'
            f'<path class="draw{" t" if teal else ""}" pathLength="1" d="{d}" stroke-width="6" style="--dd: {dd}; --d: 99s"{da}/></svg>')


def build(pages, dst, styles, keys, picks):
    css = "\n".join((SRC / f).read_text(encoding="utf-8") for f in styles)
    js = (SRC / "common.js").read_text(encoding="utf-8")
    for name, out in pages.items():
        if picks and name not in picks:
            continue
        p = SRC / f"{name}.body.html"
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8")
        body = re.sub(r"<!--@art (s\d\d)((?: [^>]+?)?)-->", lambda m: art(m, keys), body)
        body = re.sub(r"<!--@bg (\S+)((?: [^>]+?)?)-->", lambda m: bg(m.group(1), (m.group(2) or "").split()), body)
        body = re.sub(r"<!--@flip (s\d\d)((?: [^>]+?)?)-->", lambda m: flip(m, keys), body)
        body = re.sub(r"<!--@eeg (-?[\d.]+) (-?[\d.]+) ([\d.]+) ([\d.]+) (\d+)((?: [^>]+?)?)-->", eeg, body)
        html = ("<!doctype html>\n<!-- Собрано assets/src/build.py — правьте исходники. -->\n"
                '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
                + '\n<div class="film" data-backdrop></div>\n<script>\n' + js + "\n</script>\n</body></html>\n")
        (dst / f"{out}.html").write_text(html, encoding="utf-8")
        print(dst / f"{out}.html")


build(PAGES, OUT, ("common.css", "live.css", "gold.css"), kie_keys(), sys.argv[1:])
