@echo off
rem Builds dist\PoE Tracker\PoE Tracker.exe (a folder you can move anywhere).
rem Run "Start PoE Tracker.bat" once first so the environment exists.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check pyinstaller || (pause & exit /b 1)
".venv\Scripts\nicegui-pack.exe" --onedir --windowed --noconfirm --name "PoE Tracker" ^
  --add-data "poetracker\defaults;poetracker\defaults" ^
  --add-data "poetracker\migrations;poetracker\migrations" ^
  --add-data "poetracker\ui\static;poetracker\ui\static" ^
  poe_tracker.py
echo.
echo Done. Your app is in: %~dp0dist\PoE Tracker\PoE Tracker.exe
pause
