# Video Studio (MVP)

**Начните с [`START_HERE.md`](START_HERE.md)** — как запустить у себя, карта архива, что проверено, что дальше.

Пишешь тему — получаешь MP4: озвучка (ru по умолчанию, язык настраивается: `language` в `project.yaml`), анимация, нарисованная кодом, субтитры, музыка,
автоматическая проверка. Короткие ролики — за одну сессию, длинные (до часа) — по главам.

## Быстрый старт
```bash
cd video-studio
pip install -r requirements.txt          # numpy, Pillow, PyYAML (+ ffmpeg в системе)
python -m studio doctor                   # что работает на этой машине
bash tools/setup_rhvoice.sh               # один раз: офлайн-голос RHVoice (сборка ~5–10 мин)
claude                                    # открыть Claude Code в этой папке
```
В Claude Code:
```
/new-video Зашёл на минутку — потерял час, 30 секунд, вертикально
/next          # продолжить длинный ролик (следующая глава/фаза)
/chapter <slug> ch03 сделай вступление короче
/qa            # собрать, проверить, отдать
/roadmap       # следующая задача развития студии (docs/ROADMAP.md)
```
Или вручную: `python -m studio all projects/minutka`.

## Что внутри
- `CLAUDE.md` — правила для Claude (читает автоматически).
- `docs/PHASES.md` — 8 фаз с критериями «готово».
- `docs/LESSONS.md` — уроки первого прогона: что делать один раз и каких ошибок не повторять.
- `docs/ARCHITECTURE.md` — устройство и план для часовых роликов.
- `docs/SCENE_SPEC.md` — формат сценария и шаблоны; `docs/TTS.md` — голоса.
- `studio/` — движок; `projects/_template/` — заготовка; `projects/minutka/` — демо 30 с (2 главы);
  `projects/habit-demo/` — горизонтальное демо на универсальных шаблонах.

## Требования
Python 3.10+, ffmpeg/ffprobe, шрифт с кириллицей (по умолчанию Inter Display; иначе DejaVu/Arial —
или `STUDIO_FONT_BOLD=/путь/к/шрифту.ttf`). Для сборки RHVoice: git, cmake, g++ (Linux; на macOS —
Xcode CLT; на Windows проще бэкенд `edge`: `pip install edge-tts`).
