@echo off
rem Double-click to start PoE Tracker in its own window.
rem The first run sets up Python packages (needs internet, about a minute).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: creating the Python environment...
  py -3.14 -m venv .venv 2>nul || py -3 -m venv .venv || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Could not create the environment. Is Python installed? https://www.python.org/downloads/
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
)
echo Checking packages...
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
start "" ".venv\Scripts\pythonw.exe" -m poetracker
