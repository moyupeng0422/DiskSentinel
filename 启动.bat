@echo off
cd /d "%~dp0"

:: 检查 Python 是否可用
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查依赖是否已安装
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 首次运行，正在安装依赖...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [错误] 依赖安装失败，请手动执行: pip install -r requirements.txt
        pause
        exit /b 1
    )
)

:: 以管理员权限启动（扫描系统目录需要）
powershell -Command "Start-Process 'python' -ArgumentList 'main.py' -Verb RunAs -WorkingDirectory '%~dp0'"
timeout /t 3 >nul
start http://localhost:8765
