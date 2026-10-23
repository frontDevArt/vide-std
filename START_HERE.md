# START HERE — студия в двух страницах

## 1. Что это
Студия превращает **тему** в **готовый MP4**: сценарий по главам → озвучка (язык — `language` в `project.yaml`) →
анимация, нарисованная кодом → субтитры → музыка → автопроверка. Короткие ролики — за одну сессию Claude,
длинные (до часа) — по главам, по одной главе за сессию. Сейчас студия делает ролики англоязычного канала
**Notes From The Mind** (`studios/notes-from-the-mind/channel/`, пресет `lab`, голос ElevenLabs) — правила канала в `studios/notes-from-the-mind/CLAUDE.md`.

## 2. Запуск у себя
```bash
pip install -r requirements-dev.txt   # numpy, Pillow, PyYAML + pytest; нужен ffmpeg/ffprobe в системе
python -m studio doctor               # что работает на этой машине (ffmpeg, шрифты, голоса, ключи)
python -m studio selftest             # регресс офлайн, ~1,5 мин: все шаблоны → MP4 → qa → сравнение с эталоном
claude                                # открыть Claude Code в этой папке
```
Голос: `elevenlabs` (ключ и голос — в `.env`, платно), `edge` (`pip install edge-tts`, нужен интернет),
офлайн — `piper` или RHVoice (`bash tools/setup_rhvoice.sh`, Linux/macOS). Подробно — `docs/TTS.md`,
установка по ОС — `docs/LOCAL_SETUP.md`. **Windows:** `PYTHONUTF8=1` в окружении, иначе вывод с кириллицей падает.

## 3. Команды в Claude CLI
| Команда | Что делает |
|---|---|
| `/new-video <тема или studios/notes-from-the-mind/briefs/<имя>.md>` | новый ролик: бриф → план → (короткий) сразу MP4 |
| `/next` | продолжить: следующая фаза или глава |
| `/chapter <slug> chNN <что изменить>` | написать/переписать одну главу |
| `/qa` | собрать, проверить, отдать |
| `/topic-radar`, `/topic-to-brief N` | недельный цикл канала: темы с источниками → бриф ролика |
| `/roadmap` | следующая задача развития: сначала `docs/REFACTOR_PLAN.md`, потом `docs/ROADMAP.md` |

Команды движка (`python -m studio …`) — в `CLAUDE.md`.

## 4. Карта
```
START_HERE.md            ← вы здесь
CLAUDE.md                правила для Claude (читается автоматически), команды движка
README.md                кратко о проекте
docs/
  WALKTHROUGH.md         полный цикл подробно: каждая команда изнутри, временные файлы, что остаётся после финала
  PHASES.md              8 фаз производства с критериями «готово»
  ARCHITECTURE.md        устройство, карта модулей, бесшовность, часовой ролик, замеры
  SCENE_SPEC.md          формат сценария, шаблоны, как писать свои
  TTS.md                 голоса и бэкенды
  LESSONS.md             уроки прогонов: каких ошибок не повторять
  LOCAL_SETUP.md         установка на Linux / macOS / Windows
  AUDIT.md               аудит 2026-10-22: замеры, баги, риски
  REFACTOR_PLAN.md       поэтапный рефакторинг с правилами «ничего не сломать»
  ROADMAP.md             развитие: мультистудия, площадки, типы роликов
  history/               SESSION_LOG.md — решения и цифры; BENCH.md — замеры скорости и диска; архив
  reference/             гайд Claude Motion и разбор, что из него берём
studio/                  движок (Python, ~7900 строк): команды — commands/, шаблоны сцен — packs/
tests/                   pytest; fixtures/gallery — все шаблоны; golden/ — эталон selftest
tools/                   setup_rhvoice.sh, bench.py (замеры)
scripts/                 weekly-radar.ps1/.sh — автозапуск радара
projects/
  _template/             заготовка нового проекта (общая для всех студий)
studios/                 студии (ROADMAP A1): `python -m studio studios` — список
  notes-from-the-mind/   канал: studio.yaml, CLAUDE.md (правила канала)
    channel/             позиционирование, стиль (STYLE.md, style-demo.html), журналы тем и визуала
    briefs/, research/   брифы роликов и недельные радары тем
    projects/fake-discounts/  живой эталон (7 минут, 4 главы, lab)
.claude/commands/        слэш-команды
.github/workflows/ci.yml CI: ruff, pytest, selftest на Ubuntu и Windows
```

## 5. Где посмотреть, что работает
- `python -m studio doctor` — что доступно на этой машине.
- `pytest` + `python -m studio selftest` — регресс движка (офлайн, голос `fake`); CI гоняет оба на Ubuntu и Windows
  при push в `master`.
- `docs/history/BENCH.md` — замеры скорости и диска; сводка — в `docs/ARCHITECTURE.md`, раздел «Замеры».
- `docs/TTS.md` — какой голос в каком состоянии.

## 6. Куда дальше
1. `docs/REFACTOR_PLAN.md` — этапы 0–4 закрыты (сетка тестов, баги, структура, скорость, диск); осталось этап 5 — документы.
2. `docs/ROADMAP.md` — несколько студий (каналы, бренды, клиенты), один ролик → все площадки (YouTube, Shorts,
   TikTok, Reels), новые типы роликов, ревью, серии, локализация, публикация.
