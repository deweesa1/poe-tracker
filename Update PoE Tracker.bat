@echo off
rem Gets the latest PoE Tracker from GitHub (github.com/deweesa1/poe-tracker).
rem Your data (database, settings, Client.txt) lives elsewhere and isn't touched.
rem Needs Git for Windows: https://git-scm.com/download/win
cd /d "%~dp0"
where git >nul 2>nul || (echo Git isn't installed. Get it from https://git-scm.com/download/win & pause & exit /b 1)
if not exist ".git" (
  echo First time: connecting this folder to GitHub...
  git init -q
  git remote add origin https://github.com/deweesa1/poe-tracker.git
  git fetch -q origin || (echo Couldn't reach GitHub. & pause & exit /b 1)
  git checkout -q -f -B main origin/main || (pause & exit /b 1)
  git branch -q --set-upstream-to=origin/main main
) else (
  git pull --ff-only || (echo. & echo Update failed: files in this folder were changed by hand. & echo Run "git status" here to see which, or delete them and run this again. & pause & exit /b 1)
)
echo.
echo PoE Tracker is up to date:
git log -1 --format="  %%h  %%s  (%%cr)"
echo Restart the tracker to use the new version.
pause
