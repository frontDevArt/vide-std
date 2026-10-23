"""P2.9: пакет commerce — ценник-бирка, чек, число с разделителями тысяч (вынесены из fake-discounts/templates/money.py)."""
from PIL import Image, ImageChops

from conftest import ROOT
from studio.packs import REGISTRY, load_project_templates
from studio.packs.commerce import CommerceNumber, PriceTag, Receipt
from studio.packs.commerce.elements import rot, thousands
from studio.packs.lab import elements

FAKE_DISCOUNTS = ROOT / "studios" / "notes-from-the-mind" / "projects" / "fake-discounts"  # ROADMAP A1

CTX = {"W": 960, "H": 540, "fps": 30, "language": "en"}
TAG = {"was": "$199", "now": "$99", "x": 480, "y": 160, "scale": 0.8, "at": 0, "strike_at": 1.0, "now_at": 1.6}
RECEIPT = {"title": "MONEY BRAIN · RECEIPT", "lines": [{"text": "ANCHOR|$1", "at": 0.5}, {"text": "TOTAL", "at": 2.0}],
           "tear_at": 3.0}


def scene(params, start=0):
    return {"chapter": "ch01", "id": "s01", "dur": 4.0, "start_frame": start, "params": params,
            "beats": [{"t0": 0.0, "t1": 4.0}], "words": []}


def render(name, params, times=(0.3, 1.2, 2.2, 3.5), state=None):
    tpl = REGISTRY[name](CTX, scene(params), state or {})
    tpl.setup()
    out = []
    for t in times:
        img = Image.new("RGBA", (CTX["W"], CTX["H"]), (0, 0, 0, 0))
        tpl.draw(img, t, t)
        out.append(img)
    return tpl, out


def test_registered():
    for name in ("commerce.price_tag", "commerce.number"):
        cls = REGISTRY[name]
        assert cls.NAMESPACE == "commerce" and set(cls.FORMATS) == {"horizontal", "vertical", "square", "portrait"}  # B3
    assert set(REGISTRY["commerce.number"].PARAMS) == set(REGISTRY["lab.full_number"].PARAMS)


def test_thousands_and_rot():
    assert thousands("$14550") == "$14,550" and thousands("$999 / 1000000") == "$999 / 1,000,000"
    x, y = rot(0, 10, 90)
    assert abs(x - 10) < 1e-9 and abs(y) < 1e-9


def test_number_sprite_has_commas(monkeypatch):
    got = []
    monkeypatch.setattr(REGISTRY["lab.full_number"], "_spr", lambda self, s, color: got.append(s))
    REGISTRY["commerce.number"](CTX, scene({"value": 14550, "prefix": "$"}), {})._spr("$14550", "accent")
    assert got == ["$14,550"]


def test_price_tag_draws_and_carries_state():
    tpl, frames = render("commerce.price_tag", {"tag": TAG, "receipt": RECEIPT, "keep": ["tag", "receipt"]})
    assert all(f.getchannel("A").getbbox() for f in frames)
    assert frames[0].tobytes() != frames[2].tobytes()  # зачёркивание и новая цена меняют кадр
    st = tpl.state_out()
    assert st["price_tag"]["was"] == "$199" and st["price_tag"]["anchor"] is False
    assert st["receipt"] == {"lines": ["ANCHOR|$1", "TOTAL"], "visible": True}
    ev = [n for _, n in tpl.sfx_events()]
    assert "swish" in ev and "tick" in ev
    # следующая сцена подхватывает бирку и чек через state
    nxt = REGISTRY["commerce.price_tag"](CTX, scene({"tag": {**TAG, "from_prev": True, "x": 300}, "receipt": {}}, 120), st)
    nxt.setup()
    assert nxt.tprev == st["price_tag"] and nxt.rc_prev == ["ANCHOR|$1", "TOTAL"] and nxt.rc_was


def test_lab_anchor_is_price_tag_with_project_state_keys():
    load_project_templates(FAKE_DISCOUNTS)
    try:
        anchor = REGISTRY["lab_anchor"]
        assert issubclass(anchor, PriceTag) and issubclass(anchor, Receipt)
        assert (anchor.TAG_STATE, anchor.RC_STATE) == ("fd_tag", "fd_receipt")  # state готового ролика не меняется
        assert issubclass(REGISTRY["fd_number"], CommerceNumber)
        # lab_anchor только с биркой и чеком рисует то же, что commerce.price_tag
        params = {"tag": TAG, "receipt": RECEIPT}
        _, a = render("lab_anchor", params)
        _, b = render("commerce.price_tag", params)
        for x, y in zip(a, b):
            assert ImageChops.difference(x, y).getbbox() is None
    finally:
        REGISTRY.drop_namespace("project")


def test_icons_moved_to_lab():
    # иконки fake-discounts теперь в lab: money.py больше не подменяет studio.lab._li
    for name in ("wheel", "house", "timer", "anchor", "receipt"):
        assert elements.line_icon(name, 40).getchannel("A").getbbox()
    src = (FAKE_DISCOUNTS / "templates" / "money.py").read_text(encoding="utf-8")
    assert "_li" not in src
