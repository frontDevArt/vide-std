"""Движение для коротких роликов (G1, студия Yereva): шаблон kit.kinetic, ключ бренд-кита motion — шторка между
сценами (render.draw_wipe) и скорость пятен фона."""
import pytest
import yaml
from PIL import Image

from studio import brand, render
from studio.packs import REGISTRY
from studio.packs.kit.kinetic import glue, tokens, word_times
from studio.style import Style


def _kit(tmp_path, **raw):
    d = tmp_path / "kit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "brand.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return d


def _style(tmp_path, **raw):
    return Style.from_cfg({"kit": brand.load(_kit(tmp_path, **raw))})


# ------------------------------------------------------------------ kit.kinetic
def test_tokens_accent_and_punctuation():
    assert tokens("Вас *ищут*, а *находят конкурентов*.") == [
        ("Вас", False), ("ищут,", True), ("а", False), ("находят", True), ("конкурентов.", True)]
    assert tokens("Вас среди них *нет.*") == [("Вас", False), ("среди", False), ("них", False), ("нет.", True)]


def test_glue_dash_to_previous_word():
    toks, tt = glue([("карты", False), ("—", False), ("чтобы", True)], [1.0, 1.5, 2.0])
    assert toks == [("карты —", False), ("чтобы", True)] and tt == [1.0, 2.0]


def test_word_times():
    words = [{"w": "а", "t0": 0.4}, {"w": "б", "t0": 0.9}, {"w": "в", "t0": 1.6}]
    assert word_times(3, words, 3.0) == [0.4, 0.9, 1.6]                     # по словам озвучки
    assert word_times(2, words, 3.0) == [0.4, 1.6]                          # другое число — внутри речи
    assert word_times(3, [], 3.0) == pytest.approx([0.2, 1.09, 1.98])       # без голоса — равномерно


def _scene(dur=3.0, **params):
    words = [{"w": w, "line": 0, "t0": 0.3 + 0.4 * i, "t1": 0.6 + 0.4 * i}
             for i, w in enumerate(["Вас", "среди", "них", "нет."])]
    return {"params": params, "dur": dur, "beats": [{"t0": 0.3, "t1": 1.9, "line": 0, "text": "Вас среди них нет."}],
            "words": words, "first": False, "last": False}


def test_kinetic_words_appear_with_speech():
    cls = REGISTRY.get("kinetic")
    ctx = {"W": 540, "H": 960, "fps": 30}
    tpl = cls(ctx, _scene(accent=["нет"]), {})
    tpl.setup()
    assert tpl.speech_on_screen and tpl.n == 4 and [it["hl"] for it in tpl.items] == [False, False, False, True]

    def ink(t):
        img = Image.new("RGBA", (540, 960), (0, 0, 0, 0))
        tpl.draw(img, t, t)
        return img.getbbox()
    assert ink(0.1) is None                       # до первого слова — пусто
    assert ink(0.7) is not None                   # «Вас» влетело
    box = ink(2.5)
    assert box[1] >= tpl.safe.y0 and box[3] <= tpl.safe.y1  # в зоне площадки


def test_kinetic_text_param_and_pages():
    cls = REGISTRY.get("kinetic")
    tpl = cls({"W": 540, "H": 960, "fps": 30}, _scene(text="Вас среди них *нет.*", size=150, lines_max=1), {})
    tpl.setup()
    assert len(tpl.pages) > 1 and tpl.items[-1]["hl"]


# ------------------------------------------------------------------ бренд-кит motion
@pytest.mark.parametrize("raw, msg", [
    ({"motion": {"transition": "zoom"}}, "motion.transition"),
    ({"motion": {"bg": 9}}, "motion.bg"),
    ({"motion": {"speed": 2}}, "motion.speed"),
])
def test_motion_errors(tmp_path, raw, msg):
    with pytest.raises(SystemExit, match=msg):
        brand.load(_kit(tmp_path, **raw))


def test_no_motion_key_keeps_kit_unchanged(tmp_path):
    """Старые киты без motion — тот же кит (и ключ кэша рендера), стиль без движения."""
    kit = brand.load(_kit(tmp_path, palette={"bg": "#102030"}))
    assert "motion" not in kit and Style.from_cfg({"kit": kit}).motion == {}


def test_bg_speed(tmp_path):
    """motion.bg — множитель времени пятен: кадр в момент T при bg: 2 = кадр в 2T у кита без motion."""
    fast = _style(tmp_path / "a", palette={"bg": "#0F1F4B"}, motion={"bg": 2.0})
    calm = _style(tmp_path / "b", palette={"bg": "#0F1F4B"})
    a, b = render._bg(64, 36, fast), render._bg(64, 36, calm)
    assert (a.speed, b.speed) == (2.0, 1.0)
    assert a.frame(3.0).tobytes() == b.frame(6.0).tobytes()


def _wipe(style, t, first=False, last=False, dur=2.0):
    img = Image.new("RGBA", (90, 160), (255, 0, 0, 255))
    render.draw_wipe(img, {"dur": dur, "first": first, "last": last}, t, style)
    return img


def test_wipe_covers_the_cut(tmp_path):
    st = _style(tmp_path, palette={"bg": "#0F1F4B", "accent": "#5B9BFF"}, motion={"transition": "wipe"})
    red = (255, 0, 0, 255)
    bg = st.col("bg_bot")
    for img in (_wipe(st, 2.0), _wipe(st, 0.0)):  # конец сцены и начало следующей — кадр закрыт целиком фоном
        assert set(img.getdata()) == {bg}
    assert set(_wipe(st, 1.0).getdata()) == {red}                  # середина сцены — без шторки
    assert set(_wipe(st, 0.0, first=True).getdata()) == {red}      # начало ролика
    assert set(_wipe(st, 2.0, last=True).getdata()) == {red}       # конец ролика
    assert set(_wipe(st, 0.0, dur=0.5).getdata()) == {red}         # короткая сцена — без шторки
    mid = _wipe(st, 1.9)
    assert red in set(mid.getdata()) and st.col("accent") in set(mid.getdata())  # наезжает: видна полоса акцента


# ------------------------------------------------------------------ логотип на карточке (plate: light)
def test_logo_plate_uses_dark_logo_on_white_card(tmp_path):
    """Логотип в цветах фона сливается с ним: plate: light — вариант для светлого фона на белой карточке, без свечения."""
    d = _kit(tmp_path, palette={"bg": "#0F1F4B"}, logo={"light": "light.png", "dark": "dark.png"})
    Image.new("RGBA", (40, 20), (255, 255, 255, 255)).save(d / "light.png")
    Image.new("RGBA", (40, 20), (26, 26, 24, 255)).save(d / "dark.png")
    st = Style.from_cfg({"kit": brand.load(d)})
    ctx = {"W": 540, "H": 960, "fps": 30, "style": st}
    scene = {"params": {"plate": "light"}, "dur": 2.0, "beats": [], "words": [], "first": False, "last": True}
    tpl = REGISTRY.get("media.logo_sting")(ctx, scene, {})
    tpl.setup()
    assert tpl.halo is None and tpl.shadow is not None
    assert tpl.logo.getpixel((2, tpl.logo.height // 2)) == (255, 255, 255, 255)        # поле карточки — белое
    assert tpl.logo.getpixel((tpl.logo.width // 2, tpl.logo.height // 2))[:3] == (26, 26, 24)  # в центре — тёмный логотип
    cta = REGISTRY.get("cta_end")(ctx, dict(scene, params={"plate": "light", "title": "Hi", "button": "Go"}), {})
    cta.setup()
    assert cta.logo.getpixel((cta.logo.width // 2, cta.logo.height // 2))[:3] == (26, 26, 24)
