@echo off
setlocal EnableExtensions
title NailQue

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo NailQue is not installed yet.
    echo Run Install-NailQue-Windows.bat first.
    pause
    exit /b 1
)

call ".venv\Scripts\python.exe" app.py
if errorlevel 1 (
    echo.
    echo NailQue exited with an error.
    pause
    exit /b 1
)
