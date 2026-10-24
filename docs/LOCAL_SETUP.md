# Установка на своём компьютере

Нужно всегда: **Python 3.12+**, **ffmpeg/ffprobe**, Python-пакеты из `requirements.txt`, Claude Code.
Шрифт: по умолчанию Inter Display (бесплатный, rsms.me/inter). Без него студия возьмёт DejaVu/Arial;
свой шрифт: `export STUDIO_FONT_BOLD=/путь/Bold.ttf` (и `_BLACK`, `_SEMIBOLD`, `_MEDIUM`, `_REGULAR`).

Версии numpy/Pillow/PyYAML закреплены точно (`pyproject.toml` = `requirements.txt`): от версии Pillow
зависят пиксели кадров, а значит кэш рендера и эталоны QA. Обновлять пины только вместе с регрессом.
Для разработки движка: `pip install -r requirements-dev.txt` (pytest, ruff) → `python -m pytest`.

После установки: `python -m studio doctor` — он реально синтезирует фразу каждым бэкендом
и предупреждает (⚠️), если установленные версии не совпадают с закреплёнными.

## Linux (Ubuntu/Debian)
```bash
sudo apt install ffmpeg git cmake build-essential python3-pip fontconfig
pip install -r requirements.txt
bash tools/setup_rhvoice.sh          # офлайн-голос; проверено
pip install edge-tts                 # опционально, нейро-голос (интернет)
pip install playwright && python -m playwright install chromium  # опционально, сцены web.html (ROADMAP C6)
```

## macOS
```bash
xcode-select --install
brew install ffmpeg cmake python
pip3 install -r requirements.txt
pip3 install edge-tts                # рекомендовано на Mac — самый простой путь к хорошему голосу
bash tools/setup_rhvoice.sh          # офлайн-голос; скрипт переносимый, но на Mac НЕ проверялся
```
Если сборка RHVoice на Mac падает — просто используйте `edge` и попросите Claude починить скрипт,
лог лежит в `tools/.build/RHVoice/build/{cfg,mk}.log`.
`fc-match` на Mac обычно нет — задайте шрифт через `STUDIO_FONT_*` или установите Inter.

## Windows
Проще всего — WSL2 (Ubuntu) и инструкция для Linux. Нативно:
```powershell
winget install Gyan.FFmpeg Python.Python.3.12
pip install -r requirements.txt edge-tts
```
и в `project.yaml`: `tts: {backend: edge, voice: ru-RU-DmitryNeural, rate: auto}`.
RHVoice нативно под Windows собирать не нужно.

## Выбор голоса
| Ситуация | Бэкенд |
|---|---|
| Есть интернет, нужен самый живой голос | `edge` (`ru-RU-DmitryNeural`, `ru-RU-SvetlanaNeural`; en: `en-US-GuyNeural`) |
| Нужен офлайн / конфиденциально | `rhvoice` (`aleksandr-hq`) или `piper` |
| Длинный ролик (час) | `edge` или `piper` — RHVoice на часе утомляет |

После смены бэкенда: `python -m studio voice <проект>` — тайминги пересчитаются, субтитры тоже.
Внимание: другой голос = другая длительность фраз, поэтому сцены перерендерятся.

## Скорость
Рендер ~8 кадров/с на ядро при 1080p. Студия использует все ядра (`render.workers` в project.yaml).
Час видео ≈ 108 000 кадров: 8 ядер ≈ 30–40 мин, 4 ядра ≈ 1–1,5 ч.
