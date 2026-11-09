"""Логотип Etagi для бренд-кита: исходник клиента etagi.svg (прислан пользователем 2026-11-01) → варианты и PNG.

    python studios/etagi/brand/logo/make_logo.py

out/etagi-white.svg — надпись белым (для тёмного фона), знак остаётся красным #FF4242;
../logo-dark.png — исходные цвета (на светлом фоне), ../logo-light.png — белая надпись (на тёмном), прозрачный фон.
Растр — headless Chromium (playwright), как у шаблона web.html.
"""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
INK, RED, WHITE = "#191919", "#FF4242", "#FFFFFF"
WIDTH = 1600  # px PNG по ширине надписи


def variants() -> dict[str, str]:
    src = (HERE / "etagi.svg").read_text(encoding="utf-8")
    assert INK in src and RED in src, "в etagi.svg ждём цвета #191919 и #FF4242"
    return {"dark": src, "light": src.replace(INK, WHITE)}


def render(svg: str, out: Path):
    from playwright.sync_api import sync_playwright
    h = round(WIDTH * 43 / 237)
    html = (f"<html><body style='margin:0;background:transparent'>"
            f"{svg.replace('width=\"237\" height=\"43\"', f'width=\"{WIDTH}\" height=\"{h}\"')}</body></html>")
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=["--disable-gpu", "--force-color-profile=srgb"])
        pg = b.new_page(viewport={"width": WIDTH, "height": h})
        pg.set_content(html)
        cdp = pg.context.new_cdp_session(pg)
        cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        pg.screenshot(path=str(out), omit_background=True)
        b.close()


def main():
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    v = variants()
    (out / "etagi-white.svg").write_text(v["light"], encoding="utf-8")
    for name, svg in v.items():
        render(svg, HERE.parent / f"logo-{name}.png")
        print("✅", HERE.parent / f"logo-{name}.png")


if __name__ == "__main__":
    main()
