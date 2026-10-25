# Ночной рендер серии (ROADMAP D2) для Планировщика заданий Windows: plan.yaml студии → очередь → утром QA.
# Ставит в очередь готовые сценарии серии и выполняет очередь (python -m studio --studio <id> batch --run).
# Сценарии пишутся днём (/new-video); ночью без присмотра только рендер. Итог утром:
#   python -m studio --studio <id> batch --list      (и python -m studio jobs — задачи и их логи)
#
# Ручной запуск:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\night-batch.ps1 -Studio acme [-Yes]
#   -Yes — согласие на платный синтез (elevenlabs) для всей серии; без него платная озвучка не пойдёт,
#          а уже озвученное днём (кэш build/tts/) денег не стоит.
# Регистрация задачи (каждую ночь в 02:00), один раз из PowerShell в корне проекта:
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\night-batch.ps1`" -Studio acme"
#   $t = New-ScheduledTaskTrigger -Daily -At 2am
#   $s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 6)
#   Register-ScheduledTask -TaskName "Studio-NightBatch-acme" -Action $a -Trigger $t -Settings $s
# Удалить: Unregister-ScheduledTask -TaskName "Studio-NightBatch-acme" -Confirm:$false
param([Parameter(Mandatory = $true)][string]$Studio, [switch]$Yes, [string]$Until = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
# В Планировщике PATH короткий: Python явно (переменная STUDIO_PYTHON, иначе python / py из PATH)
$py = $env:STUDIO_PYTHON
if (-not $py) { $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
if (-not $py) { throw "Не найден Python: задайте STUDIO_PYTHON=полный\путь\к\python.exe" }

$env:PYTHONUTF8 = "1"
Set-Location $root
# Лог пишет сама студия: studios/<id>/logs/batch-<время>.log, у каждой задачи — jobs/<id>.log
$args_ = @("-m", "studio", "--studio", $Studio, "batch", "--run")
if ($Yes) { $args_ += "--yes" }
if ($Until) { $args_ += @("--until", $Until) }
& $py @args_
exit $LASTEXITCODE
