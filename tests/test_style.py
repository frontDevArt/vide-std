"""P2.2: объект стиля вместо глобалов gfx; настройки ElevenLabs — параметром бэкенда, а не глобалом tts."""
import pickle

import pytest

from studio import gfx as G
from studio import style as SM
from studio import tts


@pytest.fixture(autouse=True)
def restore_active():
    st = SM.active()
    yield
    SM.use(st)


def test_from_cfg_matches_old_set_palette():
    st = SM.Style.from_cfg({"palette": "lab", "mood": "ember", "overrides": {"accent2": "#010203"}})
    want = dict(SM.PALETTES["lab"], **SM.mood_colors("ember", {"accent2": "#010203"}, base=SM.PALETTES["lab"]))
    assert dict(st.pal) == want
    assert st.background == "lab" and st.camera and st.subs == "karaoke"
    assert st.fonts["num"].endswith("Unbounded-VF.ttf")
    neon = SM.Style.from_cfg({})
    assert neon.palette == "neon" and neon.font == SM.DEFAULT_FONT
    assert neon.background is None and not neon.camera and neon.fonts == {}


def test_style_is_value_and_readonly():
    a = SM.Style.from_cfg({"palette": "lab", "overrides": {"glow_cool": "#000001"}})
    b = SM.Style("lab", None, (("glow_cool", "#000001"),))
    assert a == b and hash(a) == hash(b)
    assert a != SM.Style("lab")
    with pytest.raises(TypeError):
        a.pal["accent"] = (0, 0, 0)
    c = pickle.loads(pickle.dumps(a))  # воркеры рендера получают стиль в ctx
    assert c == a and dict(c.pal) == dict(a.pal)


def test_bad_mood_fails_at_build():
    with pytest.raises(ValueError, match="нет настроения"):
        SM.Style.from_cfg({"palette": "lab", "mood": "sunny"})


def test_col_explicit_style_ignores_active():
    G.apply_style({"palette": "neon"})
    lab = SM.Style("lab")
    assert G.col("accent", style=lab) == (*SM.PALETTES["lab"]["accent"], 255)
    assert G.col("accent") == (*SM.PALETTES["neon"]["accent"], 255)


def test_sprite_caches_keyed_by_style():
    # раньше кэш спрайтов сбрасывался cache_clear при смене стиля; теперь стиль — в ключе
    neon, lab = SM.Style("neon"), SM.Style("lab")
    a = G.text_sprite("Hi", 40, color="accent", style=neon)
    b = G.text_sprite("Hi", 40, color="accent", style=lab)
    assert a is not b
    assert G.text_sprite("Hi", 40, color="accent", style=neon) is a
    G.apply_style({"palette": "lab"})
    assert G.text_sprite("Hi", 40, color="accent") is b
    assert G.font(40, family="num", style=lab).path.endswith("Unbounded-VF.ttf")


def test_compat_views_follow_active():
    G.apply_style({"palette": "lab", "mood": "night"})
    assert G.PAL["glow_cool"] == SM.MOODS["night"]["glow_cool"]
    assert G.STYLE["background"] == "lab" and G.STYLE_NAME == "lab"
    G.PAL["accent"] = (0, 0, 0)  # снимок: активный стиль не портится
    assert SM.active().pal["accent"] == SM.PALETTES["lab"]["accent"]
    G.set_palette("calm")
    assert G.PAL["accent"] == SM.PALETTES["calm"]["accent"]


def test_template_reads_ctx_style():
    from studio.templates import Template
    lab = SM.Style("lab")
    t = Template({"W": 1920, "H": 1080, "fps": 30, "style": lab}, {"dur": 1.0, "beats": []}, {})
    assert t.style is lab


def test_elevenlabs_cfg_is_a_parameter(tmp_path, monkeypatch):
    assert not hasattr(tts, "_EL_CFG")
    seen = {}

    def fake_el(text, voice, rate, out_raw, cfg=None):
        seen.update(cfg or {})
        out_raw.write_bytes(b"\0" * 2000)

    monkeypatch.setitem(tts.BACKENDS, "elevenlabs", fake_el)
    monkeypatch.setattr(tts, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    cfg = {"backend": "elevenlabs", "voice": "V", "context": True, "elevenlabs": {"stability": 0.3}}
    with pytest.raises(RuntimeError, match="stop"):
        tts.synth("Now.", cfg, 100, tmp_path, prev="Before.", nxt="After.")
    assert seen["previous_text"] == "Before." and seen["next_text"] == "After."
