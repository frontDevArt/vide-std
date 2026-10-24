"""Шаблон web.html (ROADMAP C6, спайк): тело сцены — страница HTML/CSS, кадр из headless Chromium.

Страница видит `window.SCENE`: dur, fps, W, H (CSS px, короткая сторона 1080), beats [{text, t0, t1}],
words [{w, t0, t1}], vars (params.vars), area и safe (рабочая зона и безопасная, CSS px), t — время кадра.
В :root — переменные `--dur`, `--b0`…`--bN` (начала битов, `s`), `--e0`… (концы), `--v-<имя>` (params.vars),
цвета палитры `--c-<имя>` (`--c-accent`, `--c-text`…) и шрифт `--font` (семейство `studio`, файлы стиля):
`animation-delay: var(--b1)` — анимация со второго бита. Свой ход времени — `window.seek = (t, S) => {…}`.
Фон страницы — прозрачный: под ней наш фон, над ней — субтитры.
"""
from __future__ import annotations

from pathlib import Path

from ... import assets as AS
from ... import gfx as G
from ..base import Template
from ..registry import P, template
from . import browser as B


def _css(style, beats, dur, vars_, zoom):
    fonts = []
    for w, n in G.WEIGHT_NUM.items():
        try:
            f = G._font_file_for(w, style.font)
        except RuntimeError:
            continue
        fonts.append(f"@font-face{{font-family:studio;font-weight:{n};src:url('{Path(f).resolve().as_uri()}')}}")
    var = {"--dur": f"{dur:.3f}s", "--font": "studio, sans-serif"}
    for i, b in enumerate(beats):
        var[f"--b{i}"], var[f"--e{i}"] = f"{b['t0']:.3f}s", f"{b['t1']:.3f}s"
    for k, v in style.pal.items():
        var[f"--c-{k}"] = "#%02x%02x%02x" % tuple(v[:3])
    for k, v in (vars_ or {}).items():
        var[f"--v-{k}"] = str(v)
    var["zoom"] = f"{zoom:.6g}"  # вёрстка в «пикселях 1080»: чистовой и черновой кадр — одна страница
    return "".join(fonts) + ":root{" + ";".join(f"{k}:{v}" for k, v in var.items()) + "}"


@template("html",
          doc="Сцена из HTML/CSS (второй движок, спайк C6): страница рисуется в headless Chromium с прозрачным "
              "фоном и ложится слоем на наш фон под субтитры. Время — виртуальное: CSS-анимации и `window.seek(t)`. "
              "Нужен playwright с Chromium (не входит в requirements).",
          params={"file": P(None, "страница .html, путь от папки проекта (assets/…); в ключе кэша — только этот "
                                  "файл: CSS, JS и картинки — внутри него или --force", str),
                  "vars": P(None, "данные странице: window.SCENE.vars и CSS-переменные --v-<имя>", dict),
                  "fade": P(True, "вход и выход сцены прозрачностью слоя (как у остальных шаблонов)")},
          beats="странице: `--b0`…`--bN` в CSS и SCENE.beats (тексты и время битов), слова — SCENE.words")
class HtmlScene(Template):
    REQUIRES = "playwright"  # внешний движок: нет в фикстурах галереи и golden (кадр зависит от сборки Chromium)

    def setup(self):
        if not self.p.get("file"):
            raise ValueError(f"web.html {self.s.get('id')}: нужен params.file — страница .html")
        self.file = AS.path(self.ctx.get("roots") or ["."], self.p["file"])
        if not self.file.is_file():
            raise FileNotFoundError(f"web.html {self.s.get('id')}: нет страницы {self.p['file']}")
        z = min(self.W, self.H) / 1080
        box = lambda b: {k: round(getattr(b, k) / z, 1) for k in ("x0", "y0", "x1", "y1")}  # noqa: E731
        self.scene = {"dur": self.D, "fps": self.fps, "W": round(self.W / z), "H": round(self.H / z),
                      "beats": [{"text": b.get("text", ""), "t0": b["t0"], "t1": b["t1"]} for b in self.beats],
                      "words": [{"w": w["w"], "t0": w["t0"], "t1": w["t1"]} for w in self.s.get("words") or []],
                      "vars": self.p.get("vars") or {}, "area": box(self.area), "safe": box(self.safe), "t": 0.0}
        self.css = _css(self.style, self.beats, self.D, self.p.get("vars"), z)
        self.key = (str(self.file), self.s.get("key") or self.s.get("hash"), self.W, self.H)

    def layer(self, t):
        pg = B.page(self.key, self.file, self.W, self.H, self.scene, self.css)
        img = B.shot(pg, t, self.W, self.H)
        k = self.io(t) if self.p.get("fade", True) else 1.0
        if k < 1:
            img.putalpha(img.getchannel("A").point(lambda a: int(a * k + 0.5)))
        return img

    def draw(self, img, t, T):
        lay = self.layer(t)
        if img.mode == "RGBA":
            img.alpha_composite(lay)
        else:
            img.paste(lay, (0, 0), lay)
