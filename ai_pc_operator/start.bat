@echo off
REM Screen-AI Startup Script for Windows

echo ========================================
echo Screen-AI: Local AI PC Operator
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

REM Navigate to backend
cd /d "%~dp0backend"

REM Install dependencies if needed
if not exist ".installed" (
    echo Installing dependencies...
    pip install -r requirements.txt
    python -m playwright install chromium
    echo. > .installed
    echo Dependencies installed.
    echo.
)

REM Get local IP for mobile access
echo Finding your IP address...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)

:found
echo.
echo ========================================
echo Server starting...
echo ========================================
echo.
echo Local access:    http://localhost:8000
echo Mobile access:   http://%IP%:8000
echo.
echo Pairing code will appear below.
echo Open the mobile URL on your phone.
echo ========================================
echo.

REM Start server
python -m app.main

pause
