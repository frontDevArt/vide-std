---
description: Мастер новой студии — тип, ниша, площадки, языки, голос, бренд-кит по референсу и утверждённое демо стиля
argument-hint: "<описание канала/бренда/клиента> [скриншоты, логотип, сайт]"
---
Пользователь хочет новую студию (канал, бренд или клиента): $ARGUMENTS

Работай по корневому CLAUDE.md, docs/BRAND.md (свой стиль по референсу) и ROADMAP A1–A4. Итог — `studios/<id>/` с
`studio.yaml`, `brand/brand.yaml`, `CLAUDE.md` студии (для youtube — `channel/POSITIONING.md`) и **утверждённое демо
стиля 10–15 с**. Всё за одну сессию.

1. **Анкета — из описания, не допросом.** Вытащи из $ARGUMENTS и приложенных файлов:
   - id (латиница, дефис), название; тип `youtube | brand | client`;
   - ниша/продукт, зритель, тон; чего нельзя;
   - площадки (`youtube`, `youtube-shorts`, `tiktok`, `instagram-reels`, …) → формат по умолчанию
     (youtube — horizontal, короткие площадки — vertical);
   - языки роликов (первый — по умолчанию);
   - голос: бэкенд и ID голоса. ElevenLabs — платный: только если пользователь попросил; ключ и ID голоса пользователь
     кладёт сам в `studios/<id>/.env` (`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`) — в чат их не просить и не выводить.
     Без ElevenLabs — edge (`python -m studio doctor` покажет, что работает). Голос по умолчанию — мужской
     (en: `en-US-AndrewMultilingualNeural`, ru: piper `ru_RU-ruslan-medium` или edge `ru-RU-DmitryNeural`).
   - референсы стиля: описание, логотип, скриншоты сайта/упаковки/ролика-ориентира.
   Нет ответа без пользователя (например, тип или язык совсем неясны) — **один** вопрос со всеми пробелами сразу;
   остальное реши сам и запиши в `CLAUDE.md` студии.
2. `python -m studio doctor`. Нет ни одного рабочего голоса для языка студии — сказать пользователю и остановиться.
3. `python -m studio new-studio <id> --name "<название>" --kind <тип> --lang <en,ru> --platforms <a,b> [--format …]
   [--tts edge --voice <ID>]` — заготовка студии и проект демо `projects/<id>-style/`.
4. **Бренд-кит** `studios/<id>/brand/brand.yaml` по docs/BRAND.md, раздел «Свой стиль по референсу»:
   - HEX — пипеткой по скриншотам (`PIL.Image.getpixel`, скрипт — в scratchpad), не на глаз; фон, текст, приглушённый
     текст, 1–2 акцента; `good/warn/bad` не совпадают с акцентами;
   - логотип — копией в `brand/` (`logo: {light, dark}`), шрифты клиента — в `brand/fonts/` с лицензией, иначе OFL из
     `assets/fonts/`; фон (`gradient | solid | image | lab`), субтитры (`tiktok` для вертикали), `shape`, `cta`, `voice.tone`;
   - `python -m studio studios` — без ⚠️ у новой студии.
5. **Правила студии:** `studios/<id>/CLAUDE.md` — заполнить все TODO (ниша, зритель, обещание, нельзя/обязательно).
   Для `youtube` — `channel/POSITIONING.md` по образцу `studios/notes-from-the-mind/channel/POSITIONING.md`
   (линза, территория, стоп-лист, рубрики, формулы названий).
6. **Демо стиля 10–15 с** (как `studio demo`, STYLE §14):
   - переписать `studios/<id>/projects/<id>-style/demo/ch01.yaml` под нишу на языке студии: крючок, один факт или цифра
     продукта (без выдуманных цифр о реальном бренде — либо из описания пользователя, либо качественное утверждение),
     CTA/финальная фраза; 2–3 сцены, шаблоны с нужным форматом (`python -m studio templates`, строка «форматы»);
   - `python -m studio demo <id>-style --no-render` → `python -m studio validate <id>-style-demo` →
     `python -m studio voice <id>-style-demo` → `python -m studio stills <id>-style-demo` → **посмотреть PNG**
     (контраст, читаемость субтитров, акцент не спорит с «плохо», логотип/цвета узнаются);
   - `python -m studio demo <id>-style` (в фоне) → MP4 `studios/<id>/projects/<id>-style-demo/build/final/…`,
     QA все ✅; открыть `qa/final_frames.png`.
7. Отдать пользователю MP4 и лист stills, коротко — что взято с референса (цвета, шрифт, фон, субтитры, голос).
   **Остановиться до утверждения.** Правки — в `brand.yaml`/`demo/ch01.yaml`, снова шаг 6.
8. После «да»: в `CLAUDE.md` студии — дата утверждения и путь к демо; строка в `docs/history/SESSION_LOG.md`.
   Студию в git — только с согласия пользователя (`.env` студии в git не попадает — `.gitignore`).
   Дальше: ролик студии — `/new-video` с `python -m studio new "<тема>" --studio <id>`.
