# Register a Task Scheduler entry that auto-starts kiro-gateway at logon.
# Requires running from an elevated PowerShell (Run as administrator).
#
# Usage:
#   windows\gw-install-autostart.ps1                 # install/replace
#   windows\gw-install-autostart.ps1 -Uninstall      # remove
#
# The task runs hidden, under your current user, at every logon.

param(
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$taskName = 'KiroGateway'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Removed scheduled task '$taskName'." -ForegroundColor Green
    } else {
        Write-Host "No task named '$taskName' registered." -ForegroundColor Yellow
    }
    exit 0
}

# Require admin (Task Scheduler write requires elevation on most machines).
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltinRole]::Administrator
)
if (-not $isAdmin) {
    Write-Host "This script must run in an elevated PowerShell (Run as administrator)." -ForegroundColor Red
    exit 1
}

$repo = Split-Path -Parent $PSScriptRoot
$startScript = Join-Path $repo 'windows\gw-start.ps1'
if (-not (Test-Path -LiteralPath $startScript)) {
    Write-Host "Cannot find $startScript" -ForegroundColor Red
    exit 1
}

# Run PowerShell hidden, execute the start script.
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$startScript`"" `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Run for the current user only, with their normal privileges, keep the task
# alive across power state changes.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'Kiro Gateway (local Anthropic-compatible proxy for Claude Desktop / Kiro).' | Out-Null

Write-Host "Registered scheduled task '$taskName'. It will start at every logon." -ForegroundColor Green
Write-Host ""
Write-Host "Test it now with:  Start-ScheduledTask -TaskName $taskName"
Write-Host "Uninstall later:   windows\gw-install-autostart.ps1 -Uninstall"
