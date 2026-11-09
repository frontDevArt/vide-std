# Промпты картинок Paper Explained (Kie, `images:` сцен)

Основа — мастер-промпт пользователя «VOX-style editorial documentary» (2026-11-09) и его скриншоты-референсы
(коллаж «Global Icon / Global Impact»). Здесь — как он ложится на наш конвейер.

## Что делает модель, а что — код
| Слой кадра (снизу вверх, как в мастер-промпте) | Кто рисует |
|---|---|
| бумага с зерном | код: `brand/paper.jpg` (`brand/make_paper.py`) |
| геометрия: большой круг, кольца, тонкие линии, кресты сетки, растр | код (страница сцены): анимируется по словам |
| редакционный заголовок 1–4 слова, 20–50 % кадра, **за** предметом | код: Oswald 700, по-русски/латиницей без ошибок модели |
| главный предмет — ч/б полутоновая вырезка с белой кромкой | **Kie** (`role: subject` → `rembg`); пока сеть не даёт — SVG-заглушка кодом, замена — docs/reference/VOX_STYLE.md, «Референс 2» |
| 2–5 вспомогательных элементов | код (бумажные фишки, полоски, штамп) или Kie `subject` |
| бумажные тени, фактура | код (CSS `drop-shadow`, растр) |

Почему не целиком картинкой, как в референсе: модели коверкают кириллицу, текст и цифры правятся без
перегенерации, а слои по отдельности можно анимировать (круг растёт, заголовок поднимается, предмет падает).

## Сцена → идея → заголовок → метафора (правило мастер-промпта)
Не иллюстрировать слова буквально — показывать идею одним сильным предметом. Один главный предмет, 2–5
вспомогательных, много воздуха, понятность за 2 секунды. Заголовок — не подпись, а часть композиции.

## Стиль-блок (`images.style` в project.yaml — суффикс к каждому промпту)
```
Style: black and white editorial halftone cut-out, vintage magazine print, high contrast, visible halftone dots and
ink imperfections, cleanly isolated subject with a thin white paper cut border, premium paper collage quality,
flat even light. Isolated on a plain flat light grey background. No clutter, no text, no letters, no numbers,
no logos, no watermark, no anime, no cartoon style, no CGI look, no glossy 3D rendering, no photorealistic
background, no oversaturated colors, no distorted anatomy, no blurry details.
```
Светло-серый фон — под вырезание `rembg` (docs/IMAGES.md: тёмный объект на тёмном фоне режется плохо).

## Промпт предмета (`image: {role: subject, prompt: …}`)
Формула: `<предмет>, <состояние, которое несёт идею>, <ракурс>`. Примеры ролика `claude-limits`:
- s01 «лимит кончается к обеду» → время: `a vintage hourglass with almost all the sand already in the lower bulb, front view`
- s06 «Graphify — карта проекта» → путь: `a vintage brass pocket compass, open, seen from above`
- s07 «PonyTail — только нужный код» → лекарство: `a vintage glass pharmacy pill bottle with a plain blank label, front view`

## Палитра (пипеткой по референсу — `brand/brand.yaml`)
Бумага `#F6F0E2`, краска `#141210`, терракотовый круг `#C46557`, приглушённый синий `#5B7684`,
тёмно-синий `#30353C`, беж `#DCCDB0`, редкий приглушённый жёлтый `#E0C377`. 2–4 акцента на кадр.

## Чего нет в кадре
Логотипы брендов (в референсе — Coca-Cola; у нас нельзя), неон, градиенты, 3D, кинематографичный свет,
выдуманные цифры.
