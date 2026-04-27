@echo off
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python not found. Please install Python 3.8+
    echo Download: https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [INFO] Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install dependencies.
        echo Please run manually: pip install -r requirements.txt
        pause
        exit /b 1
    )
) else (
    echo [INFO] Checking dependencies...
    pip install -r requirements.txt -q
)

echo.
echo [INFO] Starting DiskSentinel...
echo Waiting for server to be ready...
echo.

:: Start server in background
start "" /b python main.py

:: Wait for server to respond (max 30 seconds)
set READY=0
for /l %%i in (1,1,30) do (
    if !READY!==1 goto :open_browser
    timeout /t 1 >nul
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=1)" >nul 2>&1 && set READY=1
)
:open_browser

if %READY%==1 (
    start http://localhost:8765
    echo [INFO] DiskSentinel is running at http://localhost:8765
    echo [INFO] Close this window to stop the server.
    echo.
) else (
    echo [ERROR] Server failed to start within 30 seconds.
    echo Please check the error messages above.
)
pause
