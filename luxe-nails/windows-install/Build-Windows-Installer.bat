@echo off
setlocal EnableExtensions EnableDelayedExpansion
title NailQue Installer Builder

cd /d "%~dp0"

echo =====================================
echo      NailQue Windows Build Tool
echo =====================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON=python"
    ) else (
        echo Python 3 is required to build.
        pause
        exit /b 1
    )
)

if not exist ".venv\" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing build dependencies...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo pip upgrade failed.
    pause
    exit /b 1
)
call ".venv\Scripts\python.exe" -m pip install -r requirements-windows.txt pyinstaller
if errorlevel 1 (
    echo Dependency install failed.
    pause
    exit /b 1
)

echo Building NailQue.exe...
call ".venv\Scripts\python.exe" build-windows-exe.py
if errorlevel 1 (
    echo Windows executable build failed.
    pause
    exit /b 1
)

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo Inno Setup 6 is required for installer creation.
    echo Download and install it from:
    echo https://jrsoftware.org/isdl.php
    echo.
    echo After installing Inno Setup, run this script again.
    pause
    exit /b 1
)

if not exist "dist-installers\" mkdir "dist-installers"

echo Building setup installer...
"%ISCC%" "NailQue-Setup.iss"
if errorlevel 1 (
    echo Installer build failed.
    pause
    exit /b 1
)

echo.
echo Build complete:
echo dist-installers\NailQue-Setup.exe
echo.
pause
