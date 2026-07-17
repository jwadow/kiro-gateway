@echo off
REM Double-clickable launcher for kiro-gateway.
REM Runs the PowerShell start script and keeps the window open on failure so
REM you can read the error before it disappears.

setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gw-start.ps1"
if errorlevel 1 (
  echo.
  echo Gateway failed to start. Press any key to close...
  pause >nul
)
endlocal
