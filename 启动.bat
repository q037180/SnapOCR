@echo off
rem SnapOCR double-click launcher (starts GUI without console window)
cd /d "%~dp0"
start "SnapOCR" "%~dp0venv\Scripts\pythonw.exe" "%~dp0entry.py"
