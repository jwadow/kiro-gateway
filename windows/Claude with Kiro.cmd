@echo off
REM Double-clickable Claude launcher: ensures the local kiro-gateway is up,
REM then opens Claude Desktop. Point your Start Menu / taskbar shortcut at
REM this file instead of Claude.exe to make the wiring seamless.

setlocal
cd /d "%~dp0"
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass ^
  -File "%~dp0gw-launch-claude.ps1"
endlocal
