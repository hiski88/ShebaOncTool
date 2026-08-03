@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_LOCAL.ps1"
if errorlevel 1 (
  echo.
  echo Startup failed. Review the message above.
  pause
)
