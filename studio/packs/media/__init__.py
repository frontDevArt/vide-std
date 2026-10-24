"""Пакет media — фото, видео, логотип и продукт (ROADMAP C2). Файлы — ассеты проекта (`assets/` + `assets.yaml`,
studio/assets.py), декодирование — studio/media.py.

- base.py  — `MediaTemplate`: рамка `box` в долях рабочей зоны (нет — весь кадр под обрез), форма, вход/выход, подпись;
- image.py — `media.image`: Ken Burns, параллакс по слоям, проявление по маске, «до → после»;
- video.py — `media.video` (кусок видео: обрезка, скорость, звук), `media.screen` (запись экрана: зум, выноски, клики),
  `media.clip` (подкаст/интервью: звук исходника в микс, волна, караоке из расшифровки);
- brand.py — `media.logo_sting` (логотип из файла или бренд-кита), `media.product_card` (фото + цена, из commerce).

Звук исходника: у шаблона `audio_clips()` → audio.media_track кладёт его в дорожку голоса.
"""
from . import base, image, video, brand  # noqa: F401
from .base import MediaTemplate  # noqa: F401
