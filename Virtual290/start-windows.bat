@echo off
REM Virtual290 - M0 board spike launcher (Windows)
REM Serves this folder on localhost so the microphone and math fonts work.
REM Double-click this file. If SmartScreen warns: More info -> Run anyway.

setlocal
cd /d "%~dp0"
set PORT=8731
set URL=http://localhost:%PORT%/m0-board-spike.html

REM NOTE: we probe by actually RUNNING each tool, not with "where".
REM Windows 10/11 ship a python.exe stub that opens the Microsoft Store
REM instead of running Python - "where python" finds it and lies.

py -3 --version >nul 2>&1 && goto :usepy
python --version >nul 2>&1 && goto :usepython
npx --version >nul 2>&1 && goto :usenode
goto :useps

:usepy
echo.
echo   Virtual290 - board spike
echo   Serving at %URL%
echo   Leave this window open. Press Ctrl-C when you're done.
echo.
start "" "%URL%"
py -3 -m http.server %PORT%
goto :eof

:usepython
echo.
echo   Virtual290 - board spike
echo   Serving at %URL%
echo   Leave this window open. Press Ctrl-C when you're done.
echo.
start "" "%URL%"
python -m http.server %PORT%
goto :eof

:usenode
echo.
echo   Virtual290 - board spike
echo   Serving at %URL%
echo.
start "" "%URL%"
npx --yes serve -l %PORT% .
goto :eof

:useps
REM PowerShell ships with every Windows install, so this always works.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve.ps1" -Port %PORT%
if errorlevel 1 (
  echo.
  echo   Falling back to opening the file directly.
  echo   Everything works except the microphone - use the text box instead.
  echo.
  start "" "m0-board-spike.html"
  pause
)
goto :eof
