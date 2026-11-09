"""Собирает страницы сцен web.html: common.css + тело сцены + common.js → assets/<имя>.html (всё внутри файла —
так страница целиком входит в ключ кэша рендера). Запуск из корня репозитория:
python studios/paper-explained/projects/claude-limits/assets/src/build.py
"""
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent
PAGES = {"s01.body.html": "s01-hook.html", "s06.body.html": "s06-graphify.html", "s07.body.html": "s07-ponytail.html"}

css = (SRC / "common.css").read_text(encoding="utf-8")
js = (SRC / "common.js").read_text(encoding="utf-8")
for src, out in PAGES.items():
    body = (SRC / src).read_text(encoding="utf-8")
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py из common.css, " + src + ", common.js — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")
    (OUT / out).write_text(html, encoding="utf-8")
    print(OUT / out)
