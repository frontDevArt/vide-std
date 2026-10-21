# Еженедельный радар тем для Планировщика заданий Windows (вызывает scripts/weekly-radar.sh через Git Bash).
#
# Ручной запуск:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\weekly-radar.ps1 [фокус]
# Регистрация задачи (понедельник 09:00), один раз из PowerShell в корне проекта:
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PWD\scripts\weekly-radar.ps1`""
#   $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
#   Register-ScheduledTask -TaskName "NotesFromTheMind-Radar" -Action $a -Trigger $t
# Удалить: Unregister-ScheduledTask -TaskName "NotesFromTheMind-Radar" -Confirm:$false
param([string]$Focus = "")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$bash = @("$env:ProgramFiles\Git\bin\bash.exe", "${env:ProgramFiles(x86)}\Git\bin\bash.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bash) { throw "Не найден Git Bash (bash.exe). Установите Git for Windows." }

Set-Location $root
& $bash "scripts/weekly-radar.sh" $Focus
exit $LASTEXITCODE
