@echo off
rem SnapOCR launcher - works from a fresh clone (venv/ is not committed).
cd /d "%~dp0"

if exist "%~dp0venv\Scripts\python.exe" goto USEVENV
where python >nul 2>nul
if errorlevel 1 goto NOPYTHON
set "PYCHECK=python"
set "PYRUN=pythonw"
goto CHECK

:USEVENV
set "PYCHECK=%~dp0venv\Scripts\python.exe"
set "PYRUN=%~dp0venv\Scripts\pythonw.exe"

:CHECK
echo [SnapOCR] Checking dependencies...
"%PYCHECK%" -c "import PySide6, rapidocr, cv2, numpy, mss, keyboard, docx, openpyxl" >nul 2>nul
if errorlevel 1 (
  echo [SnapOCR] Installing missing dependencies from requirements.txt ...
  "%PYCHECK%" -m pip install -r requirements.txt
  if errorlevel 1 goto FAILED
)

start "" "%PYRUN%" "%~dp0entry.py"
exit /b 0

:NOPYTHON
echo [SnapOCR] Python not found.
echo Please install Python 3.10+ from https://www.python.org/downloads/
echo Then run: pip install -r requirements.txt
pause
exit /b 1

:FAILED
echo [SnapOCR] Dependency installation failed. See the message above.
pause
exit /b 1
