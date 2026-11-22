@echo off
setlocal
cd /d "%~dp0"
title DbD Rich Presence - test screenshotu

if not exist ".venv\Scripts\python.exe" goto notinstalled
if "%~1"=="" goto noargs

".venv\Scripts\python.exe" -X utf8 app\dbd_presence.py --test %*
echo.
pause
exit /b 0

:notinstalled
echo Nejdriv spust spustit.bat - provede instalaci.
pause
exit /b 1

:noargs
echo Pretahni screenshot ze hry - nebo vic screenshotu - mysi na tento soubor.
echo Vypise se, co program na obrazku precte: postava, mapa, lobby, konec zapasu.
pause
exit /b 1
