@echo off
setlocal EnableExtensions
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\build-windows.ps1"
if errorlevel 1 (
    echo.
    echo Windows build failed.
    pause
    exit /b 1
)
echo.
echo Windows build complete.
pause
