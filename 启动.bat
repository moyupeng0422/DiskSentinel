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
echo Browser will open http://localhost:8765
echo.
start http://localhost:8765
python main.py
echo.
echo [ERROR] Server stopped unexpectedly. Press any key to exit...
pause
