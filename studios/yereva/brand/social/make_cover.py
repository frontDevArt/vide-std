"""Обложка страницы Facebook Yereva: 1640×624, всё важное — в центральных ~1100 px (мобильная обрезка).
Запуск из корня репозитория: python studios/yereva/brand/social/make_cover.py"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
BRAND = HERE.parent
W, H = 1640, 624
TOP, BOT, ACCENT, DIM = (0x1D, 0x3A, 0x80), (0x0A, 0x16, 0x38), (0x5B, 0x9B, 0xFF), (0xAE, 0xBB, 0xDA)


def font(size, weight):
    f = ImageFont.truetype(str(BRAND / "fonts" / "Montserrat-VF.ttf"), size)
    f.set_variation_by_axes([weight])
    return f


img = Image.new("RGB", (W, H))
px = img.load()
for y in range(H):
    for x in range(W):
        t = min(1.0, max(0.0, (y / H) * 0.7 + (x / W) * 0.3))
        px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOT))

# мягкое пятно акцента — «солнце» справа сверху
glow = Image.new("L", (W, H), 0)
ImageDraw.Draw(glow).ellipse((1080, -260, 1620, 280), fill=90)
glow = glow.filter(ImageFilter.GaussianBlur(120))
img = Image.composite(Image.new("RGB", (W, H), ACCENT), img, glow)

# белая карточка с логотипом (логотип только на светлой подложке — правило студии)
logo = Image.open(BRAND / "logo" / "out" / "logo-dark.png").convert("RGBA")
lh = 250
logo = logo.resize((round(logo.width * lh / logo.height), lh), Image.LANCZOS)
pad = 44
cw, ch = logo.width + pad * 2, lh + pad * 2
cx, cy = 290, (H - ch) // 2
shadow = Image.new("L", (W, H), 0)
ImageDraw.Draw(shadow).rounded_rectangle((cx, cy + 14, cx + cw, cy + ch + 14), 28, fill=110)
shadow = shadow.filter(ImageFilter.GaussianBlur(22))
img = Image.composite(Image.new("RGB", (W, H), (5, 10, 30)), img, shadow)
d = ImageDraw.Draw(img)
d.rounded_rectangle((cx, cy, cx + cw, cy + ch), 28, fill="white")
img.paste(logo, (cx + pad, cy + pad), logo)

# текст справа от карточки
tx = cx + cw + 70
d = ImageDraw.Draw(img)
d.text((tx, 200), "Будьте", font=font(92, 800), fill="white")
d.text((tx, 300), "на виду", font=font(92, 800), fill=ACCENT)
d.text((tx, 425), "SMM и ролики для бизнеса в Ереване", font=font(34, 500), fill=DIM)

out = HERE / "fb-cover.png"
img.save(out)
print(out, img.size, "текст до x =", tx + d.textlength("SMM и ролики для бизнеса в Ереване", font=font(34, 500)))
