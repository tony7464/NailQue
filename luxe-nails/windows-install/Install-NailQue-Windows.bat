@echo off
setlocal EnableExtensions EnableDelayedExpansion
title NailQue Windows Installer

cd /d "%~dp0"
echo =====================================
echo    NailQue Windows Setup Installer
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
        echo Python 3 is not installed.
        echo Install Python 3.10+ from https://www.python.org/downloads/windows/
        echo and run this installer again.
        pause
        exit /b 1
    )
)

echo Using Python command: %PYTHON%
echo.

if not exist ".venv\" (
    echo Creating virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo Installing dependencies...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

call ".venv\Scripts\python.exe" -m pip install -r requirements-windows.txt
if errorlevel 1 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

if exist "..\sync_windows_bundle.py" (
    echo Syncing latest app files into windows-install...
    call ".venv\Scripts\python.exe" "..\sync_windows_bundle.py"
    if errorlevel 1 (
        echo Sync step failed.
        pause
        exit /b 1
    )
)

if not exist "logs\" mkdir "logs"
if not exist "manager_settings.json" (
    > "manager_settings.json" echo {}
)
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
    ) else (
        (
            echo AUTO_OPEN_BROWSER=true
            echo USE_DESKTOP_WINDOW=true
            echo MANAGER_PIN=1234
            echo PORT=5001
            echo HOST=0.0.0.0
        ) > ".env"
    )
)

echo Creating desktop launcher shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws=New-Object -ComObject WScript.Shell; $s=$ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\NailQue.lnk'); $s.TargetPath='%CD%\Start-NailQue.bat'; $s.WorkingDirectory='%CD%'; $s.Save()"

echo.
echo Installation complete.
echo Double-click Start-NailQue.bat to launch the app.
echo A NailQue desktop shortcut was also created.
echo.
pause
