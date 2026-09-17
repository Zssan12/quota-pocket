@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
where py >nul 2>nul
if not errorlevel 1 (
  py -3 windows_launcher.py
) else (
  python windows_launcher.py
)
if errorlevel 1 pause
