---
description: Собрать финал и проверить его перед отправкой
argument-hint: "[slug проекта]"
---
Проект: $ARGUMENTS

1. `python -m studio status` — если есть устаревшие сцены, сначала `render` (в фоне).
2. `python -m studio assemble` и `python -m studio qa`.
3. Открой `qa/report.md`, `qa/subs_check.png` (если есть: без субтитров его нет), `qa/final_frames.png`.
   ⏭️ — проверка неприменима (нет речи / субтитры выключены), это не ошибка. Любой ❌ или визуальный дефект —
   исправить входы и повторить, не отдавать.
4. Всё ✅ — отправь пользователю `build/final/<slug>.mp4` и `.srt` с одной строкой итога.
