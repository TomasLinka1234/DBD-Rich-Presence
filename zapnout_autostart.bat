@echo off
setlocal
cd /d "%~dp0"
title DbD Rich Presence - zapnuti autostartu

if not exist "requirements.txt" goto wrongplace
if not exist "app\pozadi.py" goto wrongplace

echo Pripravuji program (pri prvnim spusteni se instaluje, chvili to trva) ...
call "%~dp0spustit.bat" /pripravit
if errorlevel 1 goto fail
cd /d "%~dp0"

".venv\Scripts\python.exe" -X utf8 app\pozadi.py --zapnout
if errorlevel 1 goto fail

echo.
echo Spoustim program na pozadi ...
start "" ".venv\Scripts\pythonw.exe" -X utf8 app\pozadi.py
echo.
echo ==================================================
echo   Hotovo!
echo   Program ted bezi na pozadi - ikonka je vpravo dole
echo   u hodin, pripadne pod sipkou nahoru.
echo   Po zapnuti pocitace se spusti sam a ceka,
echo   az zapnes Dead by Daylight. Okno uz nepotrebujes.
echo   Vypnuti: vypnout_autostart.bat
echo ==================================================
pause
exit /b 0

:fail
echo.
echo Neco se nepovedlo - viz vypis vyse.
pause
exit /b 1

:wrongplace
echo.
echo Vedle tohoto souboru chybi soubory programu - slozka app a requirements.txt.
echo Spust ho z rozbalene slozky DbD-Rich-Presence.
pause
exit /b 1
