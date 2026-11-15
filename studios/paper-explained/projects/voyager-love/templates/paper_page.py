"""paper_page — сцена web.html, которая сама рисует подписи (Paper Explained).

Встроенные субтитры студии рассчитаны на тёмный фон (светлый текст, тёмная плашка/обводка) — на бумаге они не
читаются. Здесь страница рисует подписи сама (assets/src/common.js: краска, звучащее слово — под жёлтым маркером),
поэтому движок их не рисует (`speech_on_screen`, как kit.kinetic; в .srt они остаются), а странице отдаётся вся
безопасная зона площадки (SCENE.area = SCENE.safe), а не только место над полосой субтитров.
Если стиль приживётся — перенести в движок как режим субтитров «marker» (docs/reference/VOX_STYLE.md, раздел 4).
"""
from studio.packs.registry import template
from studio.packs.web.html import HtmlScene


@template("paper_page",
          doc="web.html с подписями на странице (бумажный стиль): движок субтитры не рисует, странице — вся "
              "безопасная зона",
          params={k: v for k, v in HtmlScene.PARAMS.items()} if hasattr(HtmlScene, "PARAMS") else None,
          beats="как у web.html: --b0…--bN, SCENE.beats, SCENE.words")
class PaperPage(HtmlScene):
    speech_on_screen = True

    def setup(self):
        super().setup()
        self.scene["area"] = self.scene["safe"]
