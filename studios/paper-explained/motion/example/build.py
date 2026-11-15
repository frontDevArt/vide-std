"""motion-moon-demo (2026-11-16): образец подключения набора моушн-приёмов студии (studios/paper-explained/motion/).
python studios/paper-explained/projects/motion-moon-demo/assets/src/build.py [m01 m02 …]
Порядок важен: common.css, live.css (ход сцены, подписи, толчок, нырок — копия из voyager-love) → motion.css (набор:
приёмы) → moon.css (вид этого ролика, перекрывает цвета набора);  common.js → motion.js (набор) → moon.js (мир)."""
import sys
from pathlib import Path

SRC = Path(__file__).parent
OUT = SRC.parent
KIT = OUT.parents[2] / "motion"  # studios/paper-explained/motion — общий набор приёмов
PAGES = {"m01": "m01-moon", "m02": "m02-words", "m03": "m03-many", "m04": "m04-sub"}

css = "\n".join(p.read_text(encoding="utf-8") for p in (SRC / "common.css", SRC / "live.css", KIT / "motion.css", SRC / "moon.css"))
scripts = "".join("<script>\n" + p.read_text(encoding="utf-8") + "\n</script>\n" for p in (SRC / "common.js", KIT / "motion.js", SRC / "moon.js"))
for name, out in PAGES.items():
    if sys.argv[1:] and name not in sys.argv[1:]:
        continue
    body = (SRC / f"{name}.body.html").read_text(encoding="utf-8")
    html = ("<!doctype html>\n<!-- Собрано assets/src/build.py — правьте исходники. -->\n"
            '<html><head><meta charset="utf-8"><style>\n' + css + "\n</style></head><body>\n" + body
            + '\n<div class="film" data-backdrop></div>\n' + scripts + "</body></html>\n")
    (OUT / f"{out}.html").write_text(html, encoding="utf-8")
    print(OUT / f"{out}.html")
