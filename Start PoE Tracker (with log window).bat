@echo off
rem Same as Start PoE Tracker, but keeps this window open so you can see messages and errors.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run "Start PoE Tracker.bat" once first to set things up.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m poetracker %*
pause
