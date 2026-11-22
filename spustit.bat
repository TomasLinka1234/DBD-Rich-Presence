@echo off
setlocal
cd /d "%~dp0"
title DbD Rich Presence

if not exist "requirements.txt" goto wrongplace
if not exist "app\dbd_presence.py" goto wrongplace

if exist ".venv\Scripts\python.exe" goto run

echo ==================================================
echo   Prvni spusteni: instaluji, jen jednou - 2 az 5 minut
echo ==================================================
echo.

set "PYEXE="
set "PYARGS="
call :findpy
if defined PYEXE goto havepy

echo Python nenalezen - instaluji Python 3.12 pres winget ...
winget install -e --id Python.Python.3.12 --source winget --scope user --accept-package-agreements --accept-source-agreements
call :afterinstall
if defined PYEXE goto havepy

echo.
echo Winget nepomohl - stahuji instalator Pythonu primo z python.org ...
set "PYINST=%TEMP%\python-3.12.10-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $env:PYINST"
if not exist "%PYINST%" goto nopython
echo Instaluji Python 3.12 - chvili to trva, okno instalatoru se neukaze ...
start "" /wait "%PYINST%" /quiet InstallAllUsers=0 Include_launcher=0 Include_test=0 Include_doc=0 Shortcuts=0 PrependPath=0
del "%PYINST%" >nul 2>&1
call :afterinstall
if defined PYEXE goto havepy

:nopython
echo.
echo Python se nepodarilo nainstalovat automaticky.
echo Stahni a spust tenhle instalator, pak spust spustit.bat znovu:
echo   https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe
pause
exit /b 1

:havepy
echo Pouzivam Python: %PYEXE% %PYARGS%
"%PYEXE%" %PYARGS% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail
copy /y "requirements.txt" ".venv\requirements.txt" >nul
echo Instaluji volitelne rychlejsi snimani obrazovky - kdyz to selze, nevadi ...
".venv\Scripts\python.exe" -m pip install "dxcam==0.3.0" >nul 2>&1
echo.
echo Instalace hotova.
echo.

:run
rem --- po aktualizaci programu doinstalovat nove knihovny ---
fc /b "requirements.txt" ".venv\requirements.txt" >nul 2>&1
if errorlevel 1 call :syncreq
if errorlevel 1 goto syncfail
:start
if /i "%~1"=="/pripravit" exit /b 0
".venv\Scripts\python.exe" -X utf8 app\dbd_presence.py %*
if errorlevel 3 goto already
if errorlevel 1 goto crashed
exit /b 0

:already
echo.
echo Program uz bezi - bud na pozadi s ikonkou vpravo dole u hodin, nebo v jinem okne.
echo Kdyz ho chces mit tady v okne, ukonci ten druhy: prave tlacitko na ikonku, Ukoncit.
pause
exit /b 0

:syncfail
echo.
echo Nepodarilo se doinstalovat nove knihovny - zkontroluj pripojeni k internetu.
if /i "%~1"=="/pripravit" goto syncstop
echo Program spoustim i tak.
goto start

:syncstop
pause
exit /b 1

:syncreq
echo Doinstalovavam knihovny pro novou verzi programu ...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
copy /y "requirements.txt" ".venv\requirements.txt" >nul
exit /b 0

:crashed
echo.
echo Program skoncil s chybou - viz vypis vyse a soubor log.txt
pause
exit /b 1

:fail
echo.
echo Instalace selhala - viz vypis vyse.
echo Zkontroluj pripojeni k internetu a spust spustit.bat znovu.
if exist ".venv" rmdir /s /q ".venv"
pause
exit /b 1

rem --- spusteno mimo slozku programu, napr. primo ze zipu ---
:wrongplace
echo.
echo Vedle spustit.bat chybi soubory programu - slozka app a requirements.txt.
echo Nejdriv rozbal CELY zip: pravym tlacitkem na zip, Extrahovat vse.
echo Pak spust spustit.bat z rozbalene slozky DbD-Rich-Presence,
echo kde je i slozka app a soubor nastaveni.json.
echo.
echo Tato slozka: %~dp0
pause
exit /b 1

rem --- najdi Python 3.10 az 3.13 ---
:findpy
for %%V in (3.12 3.11 3.13 3.10) do call :trypy %%V
call :afterinstall
if defined PYEXE exit /b 0
python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
exit /b 0

:trypy
if defined PYEXE exit /b 0
py -%1 -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 0
set "PYEXE=py"
set "PYARGS=-%1"
exit /b 0

:afterinstall
call :trypath "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
call :trypath "%ProgramFiles%\Python312\python.exe"
exit /b 0

:trypath
if defined PYEXE exit /b 0
if exist "%~1" set "PYEXE=%~1"
exit /b 0
