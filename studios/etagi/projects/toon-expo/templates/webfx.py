"""webfx — сцена-страница HTML (как web.html) для промо с вылетами под обрез, своей речью в кадре и звуками.

Отличия от встроенного web.html:
- `speech: true` — страница сама рисует слова озвучки (кинетический текст), субтитры студии поверх не идут
  (как у kit.kinetic: `speech_on_screen`), в .srt/.vtt речь остаётся;
- «подложка под обрез»: элементы с классом `bleed` (фото на весь кадр, шторки переходов) — как фото у media.*:
  проверка «Контент в безопасной зоне» их не видит (страница получает класс `sz` на <html> и прячет `.sz .bleed`),
  проверяются только надписи и графика поверх;
- `sfx: [[t, имя], …]` — звуки студии (whoosh, swish, pop, tick, thud, riser): t — секунды от начала сцены,
  отрицательные — от конца (`-0.3` — за 0,3 с до склейки), `"b2"` — начало бита 2, `"w:слово"` — слово озвучки.
"""
from studio.packs.web import browser as B
from studio.packs.web.html import HtmlScene
from studio.templates import P, template

SOUNDS = ("pop", "tick", "whoosh", "swish", "thud", "riser")


@template("webfx",
          doc="HTML-сцена промо: страница рисует всё сама (вылеты .bleed под обрез, речь в кадре), звуки — sfx",
          params={"file": P(None, "страница .html, путь от папки проекта (assets/…)", str),
                  "vars": P(None, "данные странице: window.SCENE.vars", dict),
                  "fade": P(False, "вход и выход прозрачностью слоя (переходы рисует страница — по умолчанию нет)"),
                  "speech": P(True, "страница рисует речь сама — субтитры студии у сцены не рисуются"),
                  "sfx": P([], "звуки [[t, имя]]: t — c от начала, отрицательное — от конца, 'b2', 'w:слово'")},
          beats="странице: SCENE.beats и SCENE.words (слова озвучки со временем), --b0…--bN в CSS")
class WebFx(HtmlScene):
    def setup(self):
        super().setup()
        self.speech_on_screen = bool(self.p.get("speech", True))

    def layer(self, t):
        img = B.shot(B.page(self.key, self.file, self.W, self.H, self.scene, self.css), t, self.W, self.H)
        if self.p.get("fade", False):  # у web.html по умолчанию fade — здесь переходы рисует сама страница
            k = self.io(t)
            if k < 1:
                img.putalpha(img.getchannel("A").point(lambda a: int(a * k + 0.5)))
        return img

    def safe_draw(self, img, t, T):
        pg = B.page(self.key, self.file, self.W, self.H, self.scene, self.css)
        pg.evaluate("document.documentElement.classList.add('sz')")
        try:
            lay = self.layer(t)
        finally:
            pg.evaluate("document.documentElement.classList.remove('sz')")
        img.alpha_composite(lay) if img.mode == "RGBA" else img.paste(lay, (0, 0), lay)

    def _when(self, at):
        if isinstance(at, (int, float)):
            return at if at >= 0 else self.D + at
        s = str(at)
        if s.startswith("b") and s[1:].isdigit():
            return self.bt(int(s[1:]))
        if s.startswith("w:"):
            key = s[2:].lower()
            for w in self.s.get("words") or []:
                if w["w"].lower().strip(".,!?:;—«»\"").startswith(key):
                    return w["t0"]
        return None

    def sfx_events(self):
        ev = []
        for at, name in self.p.get("sfx") or []:
            t = self._when(at)
            if t is not None and name in SOUNDS:
                ev.append((max(0.0, t), name))
        return ev
