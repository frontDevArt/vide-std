"""Headless Chromium для шаблона web.html (ROADMAP C6): один браузер на процесс, страница на сцену.

Время — виртуальное: анимации страницы стоят на паузе, кадр t — `window.seek(t)` страницы (если есть) и
`currentTime = t` у всех анимаций документа (CSS animations, transitions, Web Animations). Часы браузера не идут,
поэтому кадр зависит только от t: рендер кусками и в нескольких процессах совпадает с рендером подряд.
Сеть закрыта: страница видит только file:// и data:.
"""
from __future__ import annotations

import atexit
import base64
import io
import json
from collections import OrderedDict
from pathlib import Path

from PIL import Image

# без GPU — растр одинаковый на любой машине; --disable-skia-runtime-opts не ставим: −35 % скорости (замер C6)
ARGS = ["--disable-gpu", "--force-color-profile=srgb", "--font-render-hinting=none", "--disable-lcd-text",
        "--hide-scrollbars"]
MAX_PAGES = 4  # открытых страниц на процесс (stills ходит по сценам; рендер — одна сцена на задачу)
_PW = _BROWSER = None
_PAGES: OrderedDict = OrderedDict()  # ключ сцены → Page

HINT = "шаблон web.html: нужен playwright с Chromium — pip install playwright && python -m playwright install chromium"

SEEK_JS = """async (t) => {
  const S = window.SCENE; S.t = t;
  if (typeof window.seek === 'function') await window.seek(t, S);
  for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
}"""


def available() -> bool:
    try:
        browser()
        return True
    except RuntimeError:
        return False


def browser():
    global _PW, _BROWSER
    if _BROWSER is None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(HINT) from e
        pw = sync_playwright().start()
        try:
            _BROWSER = pw.chromium.launch(args=ARGS)
        except Exception as e:  # нет скачанного Chromium
            pw.stop()
            raise RuntimeError(f"{HINT} ({str(e).splitlines()[0]})") from e
        _PW = pw
        atexit.register(close)
    return _BROWSER


def close():
    global _PW, _BROWSER
    for p in _PAGES.values():
        try:
            p.context.close()
        except Exception:
            pass
    _PAGES.clear()
    if _BROWSER is not None:
        try:
            _BROWSER.close()
            _PW.stop()
        except Exception:
            pass
    _PW = _BROWSER = None


def _route(route):
    url = route.request.url
    if url.startswith(("file:", "data:", "blob:")):
        route.continue_()
    else:
        route.abort()


def page(key, file, W, H, scene, css):
    """Страница сцены: окно W×H, вёрстка — в «пикселях 1080» (короткая сторона 1080 CSS px) через `zoom` корня
    (в css): одна для чистового и чернового размера. device_scale_factor < 1 headless не уменьшает снимок — черновик
    стоил бы как чистовой (замер C6). key — ключ сцены: страница переиспользуется между кадрами."""
    pg = _PAGES.get(key)
    if pg is not None:
        _PAGES.move_to_end(key)
        return pg
    ctx = browser().new_context(viewport={"width": W, "height": H})
    ctx.route("**/*", _route)
    ctx.add_init_script(f"window.SCENE = {json.dumps(scene)};")
    pg = ctx.new_page()
    pg.goto(Path(file).resolve().as_uri(), wait_until="load")
    pg.add_style_tag(content=css)
    pg.evaluate("document.fonts.ready.then(() => true)")
    cdp = ctx.new_cdp_session(pg)
    cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
    pg._studio_cdp = cdp
    _PAGES[key] = pg
    while len(_PAGES) > MAX_PAGES:
        _PAGES.popitem(last=False)[1].context.close()
    return pg


def shot(pg, t, W, H) -> Image.Image:
    """Кадр страницы в момент t сцены: RGBA W×H, фон прозрачный."""
    pg.evaluate(SEEK_JS, t)
    r = pg._studio_cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
    img = Image.open(io.BytesIO(base64.b64decode(r["data"]))).convert("RGBA")
    if img.size != (W, H):
        raise RuntimeError(f"web.html: снимок {img.size}, а кадр {W}×{H}")
    return img
