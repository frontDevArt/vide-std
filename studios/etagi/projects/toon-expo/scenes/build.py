"""Сборка страниц сцен: scenes/sNN.html (фрагмент) + lib.css + lib.js → assets/scenes/sNN.html.

    python studios/etagi/projects/toon-expo/scenes/build.py

Библиотека вклеивается в каждую страницу: в ключе кэша сцены — только её .html, поэтому правка lib.* перерисует
все сцены сама. Подстановки во фрагментах: {{logo}} — inline SVG логотипа (assets/etagi.svg), {{toon}} — логотип
выставки TOON Real Estate Expo (assets/toon-expo.svg), {{img:sNN}} — путь к
картинке Kie сцены sNN (assets/images/<ключ>.png, по imagegen). Фото и шрифты — относительными путями (../photos/…,
../fonts/…): страница открывается из assets/scenes/, сеть закрыта, file:// разрешён.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent
ROOT = PROJ.parents[3]
sys.path.insert(0, str(ROOT))


def image_paths() -> dict[str, str]:
    from studio import imagegen as IG
    from studio.project import load
    proj = load(PROJ)
    out = {}
    for where, _req, key in IG.keys(proj):
        sid = where.split("/")[-1].split("#")[0]
        out.setdefault(sid, "../images/" + IG.path(proj, key).name)
    return out


def main():
    css = (HERE / "lib.css").read_text(encoding="utf-8")
    js = (HERE / "lib.js").read_text(encoding="utf-8")
    logo = (PROJ / "assets" / "etagi.svg").read_text(encoding="utf-8")
    logo = logo.replace('width="237" height="43"', 'class="logo" preserveAspectRatio="xMidYMid meet"')
    toon = (PROJ / "assets" / "toon-expo.svg").read_text(encoding="utf-8")   # логотип выставки (SVG организатора)
    imgs = image_paths()
    out_dir = PROJ / "assets" / "scenes"
    out_dir.mkdir(parents=True, exist_ok=True)
    for frag in sorted(HERE.glob("s[0-9][0-9].html")):
        body = frag.read_text(encoding="utf-8").replace("{{logo}}", logo).replace("{{toon}}", toon)
        body = re.sub(r"\{\{img:(s\d\d)\}\}", lambda m: imgs[m.group(1)], body)
        page = ("<!doctype html><html><head><meta charset=\"utf-8\"><style>" + css + "</style></head><body>"
                "<div id=\"bg\" class=\"bleed\"></div><div id=\"tr\"></div>"
                "<div class=\"preload\"><span style=\"font-family:Mont;font-weight:900\">ПРОБА шрифта 0123</span>"
                "<span style=\"font-family:Mont;font-weight:600\">проба</span>"
                "<span style=\"font-family:Unb;font-weight:800\">13 14 15</span></div>"
                "<script>" + js + "</script>\n" + body + "\n</body></html>")
        (out_dir / frag.name).write_text(page, encoding="utf-8")
        print("✅", out_dir / frag.name)


if __name__ == "__main__":
    main()
