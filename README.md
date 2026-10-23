# Video Studio

**Начните с [`START_HERE.md`](START_HERE.md)** — как запустить у себя, команды, карта проекта, куда дальше.

Пишешь тему — получаешь MP4: озвучка (язык — `language` в `project.yaml`: ru, en, …), анимация, нарисованная кодом,
субтитры, музыка, автоматическая проверка. Короткие ролики — за одну сессию, длинные (до часа) — по главам.
Основной заказчик — англоязычный канал **Notes From The Mind** (`studios/notes-from-the-mind/channel/`).

## Быстрый старт
```bash
pip install -r requirements-dev.txt      # numpy, Pillow, PyYAML, pytest — точные версии (+ ffmpeg в системе)
python -m studio doctor                   # что работает на этой машине
python -m studio selftest                 # регресс офлайн, ~1,5 мин
claude                                    # открыть Claude Code в этой папке
```
В Claude Code:
```
/new-video studios/notes-from-the-mind/briefs/<имя>.md      # или тема: «Зашёл на минутку — потерял час, 30 секунд, вертикально»
/next          # продолжить длинный ролик (следующая глава/фаза)
/chapter <slug> ch03 сделай вступление короче
/qa            # собрать, проверить, отдать
/roadmap       # следующая задача развития студии (docs/REFACTOR_PLAN.md, затем docs/ROADMAP.md)
```
Или вручную: `python -m studio new "тема"` → сценарий → `python -m studio all <slug>`.

## Что внутри
- `CLAUDE.md` — правила для Claude (читает автоматически) и команды движка.
- `docs/PHASES.md` — 8 фаз с критериями «готово».
- `docs/LESSONS.md` — уроки прогонов: каких ошибок не повторять.
- `docs/ARCHITECTURE.md` — устройство, карта модулей, часовой ролик, замеры.
- `docs/SCENE_SPEC.md` — формат сценария и шаблоны; `docs/TTS.md` — голоса.
- `studio/` — движок; `projects/_template/` — заготовка (+ `demo/ch01.yaml` — демо стиля); `tests/` — pytest и golden.

## Требования
Python 3.12+ (golden сняты на 3.14), ffmpeg/ffprobe. Шрифты: пресет `lab` — из `assets/fonts/` (Manrope, Unbounded,
JetBrains Mono), остальные — системный с кириллицей (Inter Display, иначе DejaVu/Arial; свой —
`STUDIO_FONT_BOLD=/путь/к/шрифту.ttf`). Голос — один из бэкендов `docs/TTS.md`: `elevenlabs` (ключ в `.env`), `edge`
(`pip install edge-tts`), `piper`, RHVoice (сборка: git, cmake, g++; на macOS — Xcode CLT). Windows: `PYTHONUTF8=1`.
