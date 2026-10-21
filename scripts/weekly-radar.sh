#!/usr/bin/env bash
# Еженедельный радар тем без участия человека (канал Notes From The Mind).
# Запускает /topic-radar в Claude CLI в фоновом (headless) режиме и пишет лог.
#
# Ручной запуск:   bash scripts/weekly-radar.sh            (или с фокусом: bash scripts/weekly-radar.sh money)
# По расписанию:   Windows — scripts/weekly-radar.ps1 (Планировщик заданий), macOS/Linux — cron, см. channel/README.md

set -euo pipefail

# Корень проекта = папка на уровень выше scripts/
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
export PYTHONUTF8=1

# В Планировщике/cron PATH короткий: ищем claude явно (Windows: nvm4w; иначе — переменная CLAUDE_BIN)
CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || true)}"
[ -z "$CLAUDE_BIN" ] && [ -x /c/nvm4w/nodejs/claude ] && CLAUDE_BIN=/c/nvm4w/nodejs/claude
[ -z "$CLAUDE_BIN" ] && { echo "Не найден claude: задайте CLAUDE_BIN=/полный/путь/к/claude" >&2; exit 1; }

FOCUS="${1:-}"
mkdir -p research/radar logs
LOG="logs/radar-$(date +%Y-%m-%d).log"

# Разрешаем ровно то, что нужно радару: поиск, чтение страниц и работу с файлами проекта.
"$CLAUDE_BIN" -p "/topic-radar ${FOCUS}" \
  --allowedTools "WebSearch,WebFetch,Read,Write,Edit,Glob,Grep,Bash(date:*),Bash(mkdir:*)" \
  </dev/null >"$LOG" 2>&1

echo "Радар готов. Отчёт: research/radar/  ·  Лог: $LOG"
