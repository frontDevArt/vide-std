# Video Studio — инструкции для Claude

Ты работаешь в студии, которая превращает тему в готовый MP4 с озвучкой (язык — `language` в `project.yaml`: ru, en, …), анимацией (всё
нарисовано кодом) и субтитрами. Пользователь обычно пишет только тему. Всё остальное — твоя работа
по фазам из `docs/PHASES.md`.

## Старт любой сессии
1. `python -m studio status <проект>` (или `python -m studio studios`, если проект не назван) — что готово, что дальше.
2. Прочитай `projects/<slug>/outline.md` — там сквозные решения, их не менять без пользователя.
3. Если окружение новое: `python -m studio doctor`; нет TTS → `bash tools/setup_rhvoice.sh`.

## Команды
```
python -m studio new "<тема>" [--slug x] [--format vertical|horizontal|square|portrait] [--platform tiktok] [--duration 30] [--tts edge]
python -m studio validate <проект>         # проверка сценария
python -m studio voice    <проект> [--yes] # озвучка + тайминг (кэш); --yes — согласие на платный синтез (elevenlabs)
python -m studio stills   <проект> [--chapter chNN] [--times 1.2,3.4]   # контрольные кадры
python -m studio render   <проект> [--chapter chNN] [--draft]  # рендер сцен (кэш) — ДОЛГО, в фоне; --draft — полразмера
python -m studio assemble <проект> [--draft] [--chapters] # финальный MP4 + .srt/.vtt (--draft → build/final/<slug>.draft.mp4; --chapters — ещё build/chapters/chNN.mp4)
python -m studio qa       <проект> [--fast] # проверки + qa/*.png
# deliverables: [youtube, tiktok] в project.yaml — выходы: voice/stills/render/assemble/qa/all по всем или --out <выход>;
#   финал — output/<slug>/<выход>.mp4 в корне студии, озвучка общая (build/tts/)
python -m studio cutdown  <проект> --to youtube-shorts [--count 3] [--list] [--pick ch02/s05-s08]  # нарезка → <slug>-cut-N/
python -m studio templates                 # шаблоны сцен и их параметры
python -m studio platforms [<id>]          # профили площадок: кадр, длительность, безопасная зона, громкость
python -m studio frame    <проект> <сек>    # один кадр PNG
python -m studio all      <проект> [--yes]  # voice → render → assemble → qa подряд (короткие ролики)
python -m studio demo     <проект>          # демо стиля 10–15 с в projects/<slug>-demo/ (STYLE §14)
python -m studio selftest [--full]          # регресс студии офлайн (~1,5 мин) — после правок движка
python -m studio clean    <проект> [--keep-final] [--older-than 30d] [--dry-run]  # чистка build/ с отчётом
python -m studio studios                   # студии и их проекты; --studio <id> перед командой — работать в студии
python -m studio new-studio <id> --name "…" --kind brand|youtube|client --lang en --platforms tiktok  # новая студия (мастер — /new-studio)
```
`<проект>` — slug или путь; slug без `--studio` ищется во всех студиях.

## Железные правила (каждое оплачено временем, см. docs/LESSONS.md)
- **Нет рабочего синтеза речи — сказать пользователю и остановиться.** Не делать ролик только с субтитрами.
- Речь не обрезать и не ускорять за `rate_range`. Не влезает в длительность → предложить сократить текст.
- Сначала `stills` и **посмотреть PNG**, потом полный рендер.
- Рендер и другие команды дольше ~5 минут — в фоне (`run_in_background`); ждать уведомления. Вывод каждой
  команды студия сама пишет в `projects/<slug>/logs/<команда>-<время>.log`.
  Не убивать процессы по шаблону (`pkill -f`), не ждать через `pgrep`-циклы, не обрезать вывод `| head`.
- Абсолютные пути или `cd X && cmd` в одной команде: рабочий каталог между командами сбрасывается.
- Внешним программам — `stdin` из `/dev/null`, текст для TTS — через файл.
- Не править сгенерированное в `build/` руками: менять входы (`script/*.yaml`, `project.yaml`, шаблоны)
  и перезапускать команду. Кэши сами определят, что пересчитать.
- Всё, что видно через склейку сцен, — через `state` (см. `docs/SCENE_SPEC.md`), а не локальной анимацией.
- Перед сдачей: `qa` — все ✅, открыты `qa/subs_check.png` и `qa/final_frames.png`.
- Политику сетевого прокси не обходить; 403 — не ретраить, сообщить.

## Текст для озвучки
- Строка `lines` = предложение; `|` — точки синхронизации внутри (биты).
- Пишется на языке проекта (`language`); весь ролик — один язык. Общаемся с пользователем по-русски.
- Темп — `wpm` языка из `studio/lang.py` (ru ~145, en ~155 слов/мин). Без чужого алфавита и аббревиатур
  (ru: «ютуб», не YouTube; en: без кириллицы); числа словами там, где важно произношение.
- Смена картинки каждые ~6–8 с; сцена 3–12 с.

## Длинные ролики
Одна глава за сессию: сценарий → validate → voice → stills → рендер главы в фоне. После первой главы
зафиксировать `tts.rate` числом. Подробно — `docs/ARCHITECTURE.md`, раздел «Длинный ролик».

## Развитие студии
Аудит — `docs/AUDIT.md`. Порядок работ: сначала `docs/REFACTOR_PLAN.md` (этапы 0–4 закрыты, остался этап 5 —
документы; правила «ничего не сломать» — там же и действуют дальше), потом `docs/ROADMAP.md` по вехам M1→M6
(мультистудия, площадки, типы роликов, конвейер, публикация, длинные ролики); команда `/roadmap`. «Продолжай план» (и любое «продолжай» без
названного проекта) = `/roadmap`: синхронизация с веткой этапа `stage-N` (нет её — с `master`), следующая задача, в конце — отметка [x]
в документе и коммит в `stage-N`; последний пункт этапа — merge `stage-N` в `master`, push `master` — только с согласия
пользователя. Этапы ROADMAP — по тому же правилу, ветка по букве этапа (`stage-A`, `stage-B`…). История решений
и замеры — `docs/history/SESSION_LOG.md`. Перед изменением движка прочитай `docs/LESSONS.md` и `docs/ARCHITECTURE.md`;
после — регресс: `pytest` и `python -m studio selftest` — оба ✅ (офлайн, голос `fake`, ~1,5 мин: фикстура gallery →
voice → render → assemble → qa → сравнение с `tests/golden/`, вёрстку проверяют кадры golden). Golden не обновлять
без причины: `pytest tests/test_golden.py --update-golden` — только для намеренной смены картинки, с объяснением в коммите.

## Свои шаблоны
Если встроенных не хватает — пиши `projects/<slug>/templates/<имя>.py` по контракту из
`docs/SCENE_SPEC.md`. Если шаблон удачный и общий — перенеси в `studio/templates.py`.

## Студии
Студия (workspace) — канал, бренд или клиент: `studios/<id>/` со своими `studio.yaml` (тип, языки, площадки,
`defaults:` для проектов), `CLAUDE.md` (правила студии — **прочитать перед работой с её проектами и темами**),
`channel/`, `briefs/`, `research/`, `projects/`. Корень — студия `default` (старый `projects/`). Новая студия — `/new-studio` (анкета → `new-studio` → бренд-кит по референсу → утверждённое демо стиля). Список —
`python -m studio studios`; команда в студии — `python -m studio --studio <id> <команда>` (новый проект:
`new … --studio <id>`). Настройки проекта: умолчания движка (`studio/config.py`) → `defaults:` из `studio.yaml` → `project.yaml`.
- **Notes From The Mind** (англоязычный YouTube-канал, психология: мифы под проверкой) — `studios/notes-from-the-mind/`,
  правила канала — `studios/notes-from-the-mind/CLAUDE.md`. Темы, брифы и ролики канала — только там.
