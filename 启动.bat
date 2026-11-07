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
rem Python 3.10+ is required: the code uses PEP 604 unions (X | None).
rem Without this check a 3.8 interpreter installs deps fine then dies with SyntaxError.
"%PYCHECK%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto OLDPYTHON
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

:OLDPYTHON
echo [SnapOCR] Python 3.10 or newer is required, but the interpreter found is older:
"%PYCHECK%" -c "import sys,platform; print(platform.python_version())"
echo Install Python 3.10+ from https://www.python.org/downloads/
echo If a local venv exists, delete the venv folder and run this script again.
pause
exit /b 1

:FAILED
echo [SnapOCR] Dependency installation failed. See the message above.
pause
exit /b 1
