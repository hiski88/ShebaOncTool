@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PUBLISH_TO_GITHUB.ps1"
if errorlevel 1 (
  echo.
  echo Publishing failed. Review the message above.
)
pause
