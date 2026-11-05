@echo off
setlocal enabledelayedexpansion

title NORTHSTAR -- DATA DELETION AUDIT AGENT DEMO
echo ======================================================================
echo           NORTHSTAR -- DATA DELETION AUDIT AGENT (HACKATHON DEMO)
echo ======================================================================
echo.

:: 1. Setup paths
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Locate Python executable
set "PYTHON_EXE="

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
) else if exist "C:\Users\manoh\AppData\Local\Python\pythoncore-3.14-64\python.exe" (
    set "PYTHON_EXE=C:\Users\manoh\AppData\Local\Python\pythoncore-3.14-64\python.exe"
) else (
    where python >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        set "PYTHON_EXE=python"
    )
)

if "%PYTHON_EXE%"=="" (
    echo [ERROR] Python executable could not be found!
    echo Please install Python 3.10+ or ensure it is added to your PATH.
    pause
    exit /b 1
)

echo [OK] Using Python: %PYTHON_EXE%
echo [OK] Repository Directory: %SCRIPT_DIR%
echo.

:: 2. Check and launch Streamlit
echo [INFO] Launching NORTHSTAR Interactive Frontend...
echo [INFO] The dashboard will open in your default web browser automatically.
echo [INFO] URL: http://localhost:8501
echo.
echo Press Ctrl+C at any time in this window to stop the server.
echo ======================================================================
echo.

"%PYTHON_EXE%" -m streamlit run frontend\app.py --server.port 8501 --server.headless false --browser.gatherUsageStats false

pause
