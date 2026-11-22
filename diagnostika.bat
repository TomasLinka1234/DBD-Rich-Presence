@echo off
setlocal
cd /d "%~dp0"
title DbD Rich Presence - diagnostika

if not exist ".venv\Scripts\python.exe" goto notinstalled

".venv\Scripts\python.exe" -X utf8 app\dbd_presence.py --diagnostika
echo.
pause
exit /b 0

:notinstalled
echo Nejdriv spust spustit.bat - provede instalaci.
pause
exit /b 1
