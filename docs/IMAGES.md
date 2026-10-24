# Картинки для сцен (ROADMAP C5)

Картинку генерирует модель, анимирует наш Python (шаблон `media.image`). Включается на ролик: `images.enabled` в
`project.yaml`. Платно — только после сметы и «да» пользователя. Здесь — выбор сервиса и модели (C5.1, 2026-10-24).

## Сервис: Kie AI
Агрегатор моделей (Google, ByteDance, BFL, OpenAI, Recraft…) с одним API и одним ключом `KIE_API_KEY` (`.env`).
- Задача: `POST https://api.kie.ai/api/v1/jobs/createTask` `{model, input}` → `data.taskId`.
- Статус: `GET /api/v1/jobs/recordInfo?taskId=…` → `state`: `waiting | queuing | generating | success | fail`;
  ссылки — `resultJson.resultUrls` (строка JSON), цена — `creditsConsumed`. Задача без результата 10 мин → код 408.
- **Ошибка приходит с HTTP 200** — смотреть поле `code`; 402 — нет кредитов.
- Баланс: `GET /api/v1/chat/credit` → `data` (кредиты). Смету сверять с ним до и после.
- Свои картинки на вход (правка, раскладка на слои, референс стиля) — только URL: загрузка
  `POST https://kieai.redpandaai.co/api/file-stream-upload` (multipart) → `data.downloadUrl`; файл живёт 24 ч.
- Курс: **200 кредитов = $1**. Документация: `docs.kie.ai` (полный список — `docs.kie.ai/llms.txt`).

## Модели-кандидаты
Цены — по странице Kie или замеру `creditsConsumed`; «?» — не опубликовано, уточнить замером.

| Модель (`model`) | Что делает | Цена за картинку | Плюсы | Минусы |
|---|---|---|---|---|
| `google/nano-banana` | текст → картинка, ~1024 px | 4 кр = **$0.02** (замер C5.0) | дёшево, держит палитру из hex, текста нет | мало пикселей для 1080p, нет сида и референса |
| `google/nano-banana-edit` | правка по картинкам-входам (до 10) | ? (пример — 3 кр) | «та же сцена, но…» → `state_b`, `before_after` | вход — только URL (загрузка) |
| `nano-banana-2` | текст + до 10 референсов, 1K/2K/4K | 8 / 12 / 18 кр = $0.04 / **$0.06** / $0.09 | 2K хватает на 1080p; референс держит стиль ролика | дороже в 3 раза |
| `flux-3/klein-text-to-image` (+ `klein-edit-image`) | текст → картинка, 1K/2K/4K, `seed` | 1.6 / 2.5 / 6.5 кр = $0.008 / $0.0125 / $0.0325 | самый дешёвый, есть сид | лицензия весов BFL на «Klein» не проверена; стиль не проверен |
| `seedream/5-flash-layer-decomposition` | картинка → базовая + слои PNG с `bounding_box` | ~1 картинка за слой (пример — 13 кр) | **сцена целиком → слои**: один ракурс у фона и объекта (боль C5.0) | прозрачность слоёв в документации не обещана — проверить |
| `recraft/remove-background` | вырезание фона | ? (пример — 1 кр) | без локальной модели | вход ≤ 5 МБ, выход, судя по примеру, webp |

Ещё есть Seedream 5 (Flash/Lite/Pro), Imagen 4, GPT Image 2/2.5, Ideogram V3, Qwen, Wan 2.7 — без явного
преимущества для плоской векторной иллюстрации; смотреть, если основные не подойдут.

## Вырезание объекта: локально
`rembg` + `isnet-general-use` (179 МБ, Apache-2.0) в отдельном `tools/rembg-venv/` — бесплатно, офлайн, чисто на
плоской иллюстрации (C5.0). Свой venv: в окружении студии `rembg` поднял бы Pillow (риск для golden). В venv стоит
onnxruntime 1.20.1: свежий падает при импорте на системном VC++ runtime 14.32 (нужен 14.40+). Модель качается в
`~/.rembg/models/` с релизов GitHub `danielgatis/rembg`, md5 проверяется. Не брать `bria-rmbg` — некоммерческая.
Запасной вариант — `recraft/remove-background` у Kie.

## Лицензия (монетизируемые ролики)
- **Kie AI** (Terms of Use): о правах на сгенерированное **молчит** — есть только «You retain ownership of your User
  Content»; права на выход — по условиям поставщика модели. Перед первым роликом для клиента — письменный ответ поддержки
  Kie (Discord/Telegram из кабинета), записать сюда.
- **Google (Nano Banana):** условия Gemini API, раздел «Use of Generated Content» — Google не претендует на
  сгенерированное; ответственность за использование — на нас. Коммерческое использование не запрещено.
- **BFL (FLUX):** у открытых весов разные лицензии ([dev] — некоммерческая); для Klein через Kie не проверено → не
  умолчание.
- **ByteDance (Seedream), Recraft:** не проверено.
- В `assets.yaml` у каждой картинки: модель, промпт, цена, лицензия — «Google Gemini API terms (через Kie AI)» и т. п.

## Умолчание
```yaml
images:
  backend: kie
  model: nano-banana-2      # 2K: $0.06 за картинку; ролик 10–20 картинок ≈ $0.6–1.2 при budget_usd: 3
  resolution: 2K
  cutout: rembg             # rembg | kie (recraft/remove-background) | none
```
Черновики и спайки — `google/nano-banana` ($0.02). Стиль ролика держат суффикс `images.style` (hex палитры, ракурс,
«no text») и первая удачная картинка как референс (`image_input` у `nano-banana-2`).

## Открыто (сравнение на одних промптах — до C5.3)
1. `nano-banana-2` 2K с референсом стиля против `nano-banana` и `flux-3/klein`: стиль, текст на картинке, кромка.
2. `seedream/5-flash-layer-decomposition` на сцене «комната + человек»: прозрачны ли слои, годятся ли для параллакса.
3. Реальные цены `nano-banana-edit` и `recraft/remove-background` — по `creditsConsumed`.
