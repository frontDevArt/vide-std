---
description: Новый ролик по теме — бриф, план, сценарий и, если ролик короткий, сразу готовый MP4
argument-hint: "<тема> [длительность, формат, пожелания]"
---
Пользователь хочет ролик: $ARGUMENTS

Работай по CLAUDE.md и docs/PHASES.md.

Если аргумент — путь к `.md` (обычно `studios/notes-from-the-mind/briefs/<имя>.md`, шаблон `studios/notes-from-the-mind/briefs/_TEMPLATE.md`), прочитай его
целиком (и скриншоты из `studios/notes-from-the-mind/briefs/<имя>/`) — это бриф. Пустые поля реши сам, решения запиши в outline.md.
Не переспрашивай то, что в брифе уже есть.

1. `python -m studio doctor`. Если ни один TTS не работает — `bash tools/setup_rhvoice.sh` (в фоне, долго).
   Если и после этого синтеза нет — сообщи пользователю и остановись.
2. Фаза 1. Определи из запроса язык ролика (по умолчанию ru; язык запроса ≠ язык ролика), длительность и формат. Если не сказано: до 60 с → vertical и
   точная длительность; длиннее → horizontal, `target_duration: null`. Один уточняющий вопрос —
   только если без ответа нельзя (например, неясно 30 секунд или 30 минут).
   Картинки: нужны ли AI-иллюстрации (docs/IMAGES.md, платно) — из брифа («Картинки»), иначе нет; да — блок
   `images: {enabled: true, style: …}` в project.yaml и `image:` у сцен (docs/SCENE_SPEC.md), смета до генерации.
   Тип ролика (`python -m studio kinds`): объяснялка по умолчанию; промо, топ-N, крючок для Shorts, ролик под музыку — `--kind`.
   `python -m studio new "<тема>" --slug <латиница> [--kind <тип>] --format <...> [--duration N] [--lang en] [--tts elevenlabs]`,
   заполни project.yaml (поля `brief:` типа — `new` их напечатает). «Не упоминать / избегать», «Чего в визуале НЕ надо»
   и «Готово, если» из брифа — в `avoid:` / `done_means:` (правило-словарь, где проверяемо: `{max_words_on_screen: 6}`,
   `{words: [...]}`, `{final_hold: 1.5}`…; остальное строкой — в чек-лист qa), docs/PHASES.md, фаза 1.
   Для языка без рабочего голоса (`doctor` покажет) — сказать пользователю и остановиться.
3. Фаза 2. outline.md: идея, главы с бюджетом слов (`wpm` языка из studio/lang.py: ru ~145, en ~155), визуальная линия, сквозные решения.
4. Если ролик ≤ 3 минут — пройди фазы 3–8 до конца в этой сессии (рендер в фоне, stills смотри глазами,
   QA должен быть весь ✅) и отдай MP4 + .srt.
   Если длиннее — напиши сценарий ПЕРВОЙ главы, сделай voice + stills, запусти рендер главы в фоне,
   и скажи пользователю: «дальше — /next».
5. Канал Notes From The Mind (бриф с `Пресет: lab`, обычно из `/topic-to-brief`): проект — в студии канала,
   `python -m studio new "<тема>" --studio notes-from-the-mind …` → `studios/notes-from-the-mind/projects/<slug>/`
   (язык и голос по умолчанию — из её `studio.yaml`; правила — `studios/notes-from-the-mind/CLAUDE.md`). `language: en`, `style.palette: lab`,
   `loudness: -14`, `subtitles.size: 36`, голос — ElevenLabs (`tts.backend: elevenlabs`, `rate` числом; без ключа в `.env` —
   сказать пользователю и предложить edge `en-US-AndrewMultilingualNeural`). Раскадровка по `docs/SCENE_SPEC.md`, раздел
   «Шаблоны канала»: шаблон композиции `lab_*` на каждую сцену (из раздела 4 брифа), каждый элемент привязан к слову-триггеру
   (`at: "66"`), разрыв ритма каждые 20–30 с, чек-лист `studios/notes-from-the-mind/channel/STYLE.md` §13 — до `stills`. Каждая цифра — с источником
   (`source` в сцене и список в описании).
   **Демо стиля — до сценария** (`studios/notes-from-the-mind/channel/STYLE.md` §14). Сразу после `project.yaml`, до outline-глав и сценария:
   отдельный проект `projects/<slug>-demo/` (тот же формат и стиль, 10–15 с, 2–3 сцены): главная метафора + цветовое
   настроение (`style.mood` в `project.yaml`) + новые элементы из §4 брифа + один вердикт, с настоящим голосом.
   Сценарий демо — `projects/<slug>/demo/ch01.yaml` (заготовку переписать), затем `python -m studio demo <slug> --no-render`
   → `stills <slug>-demo` (посмотреть PNG) → `python -m studio demo <slug>` (voice → render → assemble → qa). Отдать пользователю MP4 и **остановиться до утверждения**. Правки — по кругу на демо.
   После «да»: в `projects/<slug>/outline.md` раздел «Визуальная идея — утверждено» (метафора, настроение, новые элементы,
   мотив рубрики, открывающая сцена, путь к демо), строка в `studios/notes-from-the-mind/channel/visuals-log.md` со статусом `approved`. Дальше —
   фазы как обычно; внутри ролика визуальная идея не меняется.
6. В конце: одна строка — что готово, где файл, какая следующая команда.
