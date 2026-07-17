@echo off
REM Double-clickable credential refresher for Kiro Gateway.
REM
REM 1) Runs `kiro-cli login` interactively (browser flow).
REM 2) Restarts the local kiro-gateway so it picks up the new credentials.
REM 3) Verifies the gateway is healthy.
REM
REM Console stays open at the end so you can read the result. Close it when done.

setlocal
cd /d "%~dp0"

echo.
echo   Kiro Gateway - refresh credentials
echo   ---------------------------------------------------
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gw-update-creds.ps1" %*
set RC=%ERRORLEVEL%

echo.
if %RC%==0 (
  echo   Result: SUCCESS
) else (
  echo   Result: FAILED with exit code %RC%
)
echo.

echo Press any key to close this window...
pause > nul
endlocal
exit /b %RC%
