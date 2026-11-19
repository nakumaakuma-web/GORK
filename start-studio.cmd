@echo off
setlocal
cd /d "%~dp0"
:restart
where py >nul 2>nul
if not errorlevel 1 (
  py -3 app.py --port 8765
) else (
  python app.py --port 8765
)
if %errorlevel%==23 (
  echo Update installed. Restarting Prompt Extractor Studio...
  goto restart
)
if not %errorlevel%==0 pause
