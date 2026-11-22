@echo off
setlocal
cd /d "%~dp0"
title DbD Rich Presence - vypnuti autostartu

if not exist ".venv\Scripts\python.exe" goto novenv

".venv\Scripts\python.exe" -X utf8 app\pozadi.py --vypnout
".venv\Scripts\python.exe" -X utf8 app\pozadi.py --ukoncit
echo.
echo Hotovo. Po zapnuti pocitace se program uz sam nespusti.
echo Rucne ho muzes pustit pres spustit.bat (v okne)
echo nebo znovu zapnout pres zapnout_autostart.bat.
pause
exit /b 0

:novenv
echo Program jeste neni nainstalovany, neni co vypinat.
pause
exit /b 0
