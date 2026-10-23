# Студия Notes From The Mind — правила канала

Общие правила студии — корневой `CLAUDE.md`. Пути ниже — от этой папки (`studios/notes-from-the-mind/`).
Команды — из корня репозитория; slug проекта канала находится сам (`python -m studio status fake-discounts`),
новый проект — `python -m studio new "<тема>" --studio notes-from-the-mind` (язык `en` и голос ElevenLabs — из `studio.yaml`).

Студия делает ролики англоязычного YouTube-канала **Notes From The Mind** (психология: мифы под проверкой).
- Ниша, стоп-лист, рубрики, вердикты, формулы названий — `channel/POSITIONING.md`. Это закон для выбора тем.
- Визуал — пресет `lab` по `channel/STYLE.md` (эталон движения — `channel/style-demo.html`, шаблоны `lab_*`).
- **Каждый факт и каждая цифра — с источником** `(Авторы, год)`; нет источника — нет факта. Источники — в описание ролика.
- **Язык роликов канала — английский** (`language: en`). Общение с пользователем и служебные тексты — по-русски.
- Голос — ElevenLabs (`tts.backend: elevenlabs`; ключ и голос только в `.env`, в чат и в git не выводить).
- Недельный цикл: `/topic-radar` → `research/radar/<ГГГГ-Wнн>.md` → `/topic-to-brief N` → `briefs/<имя>.md` →
  `/new-video briefs/<имя>.md` → в `channel/topics-log.md` статус `published`/`rejected`.
- Автозапуск радара — `scripts/weekly-radar.ps1` в корне (Планировщик заданий), лог в `logs/`.
