@echo off
rem PoE Tracker in developer mode: Settings gets a Developer card that can force
rem League Start to any league and phase. Keeps this window open for messages.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run "Start PoE Tracker.bat" once first to set things up.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m poetracker run --dev %*
pause
