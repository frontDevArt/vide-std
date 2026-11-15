"""Настоящее фото → бумажная вырезка канала: ч/б, контраст, лёгкий газетный растр, обрезка по силуэту.
python studios/paper-explained/projects/nvidia-huang-demo/assets/src/people.py  (вход — people/<имя>.cut.png от rembg)"""
from pathlib import Path
from PIL import Image, ImageOps, ImageChops, ImageDraw, ImageFilter

P = Path(__file__).parent.parent / "people"
for src in P.glob("*.cut.png"):
    im = Image.open(src).convert("RGBA")
    a = im.getchannel("A").point(lambda v: 0 if v < 60 else v)
    im = im.crop(a.getbbox()); a = a.crop(a.getbbox())
    s = 1200 / im.height
    im = im.resize((round(im.width * s), 1200), Image.LANCZOS); a = a.resize(im.size, Image.LANCZOS)
    g = ImageOps.autocontrast(ImageOps.grayscale(im), cutoff=1)
    g = g.point(lambda v: int(255 * (v / 255) ** 1.15))
    # растр: точки 6 px, размер по тёмному — смешиваем 30 % с фото, лицо остаётся узнаваемым
    dots = Image.new("L", g.size, 255); d = ImageDraw.Draw(dots); step = 6
    small = g.resize((g.width // step + 1, g.height // step + 1), Image.BILINEAR)
    for y in range(small.height):
        for x in range(small.width):
            r = (1 - small.getpixel((x, y)) / 255) * step * .62
            if r > .4:
                cx, cy = x * step + (step / 2 if y % 2 else 0), y * step
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=0)
    g = Image.blend(g, ImageChops.multiply(g, dots), .3)
    out = Image.merge("RGBA", (g, g, g, a.filter(ImageFilter.GaussianBlur(.6))))
    out.save(P / src.name.replace(".cut.png", ".ht.png"))
    print(P / src.name.replace(".cut.png", ".ht.png"), out.size)
