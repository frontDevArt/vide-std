"""Пакет commerce: шаблоны price_tag (ценник «было → стало» + чек) и number (число с единицей и разделителями тысяч)."""
from __future__ import annotations

from PIL import ImageDraw

from ..lab.base import LabTemplate
from ..lab.templates import LabFullNumber
from ..registry import P, template
from .elements import thousands
from .receipt import RECEIPT_DEFAULTS, Receipt
from .tag import TAG_DEFAULTS, PriceTag


@template("price_tag",
          doc="Ценник-бирка на верёвочке: падает от гвоздика у верха зоны и качается, старая цена зачёркивается accent-2, новая "
              "выпрыгивает пружиной; опц. чек из принтера справа (строки по триггерам, отрыв крупным планом). "
              "Бирка и чек переходят через склейку (tag.from_prev / keep: [tag, receipt]).",
          params={"tag": P(dict(TAG_DEFAULTS), "бирка {was, now, x, y, scale, at, strike_at, now_at, from_prev, "
                                               "was_label, now_label}; y — длина верёвки до люверса", dict),
                  "receipt": P(None, "чек {title, lines: [{text: 'СЛЕВА|СПРАВА', at}], at, tear_at, tear_to}; "
                                     f"пример: {RECEIPT_DEFAULTS}", dict),
                  **LabTemplate.COMMON},
          beats="всё по словам-триггерам `at`; receipt.tear_at — чек отрывается и выезжает в tear_to "
                "(строка без «|» — итог по центру)")
class PriceTagScene(PriceTag, Receipt, LabTemplate):
    def plan_body(self):
        self.tag_plan()
        self.receipt_plan()

    def state_out(self):
        out = super().state_out()
        self.plan()
        out[self.TAG_STATE] = self.tag_state()
        out[self.RC_STATE] = self.receipt_state()
        return out

    def sfx_body(self):
        return self.tag_sfx() + self.receipt_sfx()

    def setup_body(self):
        if self.tg:
            self.tag_setup()

    def draw_body(self, img, t, T):
        vd = self.vdim(t)
        if self.tg:
            self.draw_tag(img, ImageDraw.Draw(img, "RGBA"), t, T, vd)
        self.draw_receipt(img, t, T, vd)


@template("number",
          doc="lab · Full Number для цен и сумм: числа ≥ 1000 с запятыми ($14,550). Единица — prefix/suffix "
              "(0,77 $ → value 77 + suffix ¢).",
          params=dict(LabFullNumber.PARAMS),
          beats=LabFullNumber.BEATS)
class CommerceNumber(LabFullNumber):
    def _spr(self, s, color):
        return super()._spr(thousands(s), color)

    def _str(self, v):
        return thousands(super()._str(v))
