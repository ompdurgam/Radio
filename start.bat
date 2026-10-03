@echo off
title Delux Radio -- 90s Bollywood Radio Station
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

echo.
echo  ██████╗ ███████╗██╗     ██╗   ██╗██╗  ██╗
echo  ██╔══██╗██╔════╝██║     ██║   ██║╚██╗██╔╝
echo  ██║  ██║█████╗  ██║     ██║   ██║ ╚███╔╝ 
echo  ██║  ██║██╔══╝  ██║     ██║   ██║ ██╔██╗ 
echo  ██████╔╝███████╗███████╗╚██████╔╝██╔╝ ██╗
echo  ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝
echo.
echo  DELUX RADIO -- 90s Bollywood Radio Station
echo  ---------------------------------------------

:: Parse command-line arguments
set SEED_CHOICE=
:parse_args
if "%~1"=="" goto after_args
if /i "%~1"=="--seed" set SEED_CHOICE=seed& shift& goto parse_args
if /i "%~1"=="-s" set SEED_CHOICE=seed& shift& goto parse_args
if /i "%~1"=="--no-seed" set SEED_CHOICE=no-seed& shift& goto parse_args
if /i "%~1"=="--empty" set SEED_CHOICE=no-seed& shift& goto parse_args
if /i "%~1"=="-n" set SEED_CHOICE=no-seed& shift& goto parse_args
if /i "%~1"=="--help" goto show_help
if /i "%~1"=="-h" goto show_help
shift
goto parse_args

:show_help
echo Usage: start.bat [OPTIONS]
echo   --seed, -s      Start and seed songs into catalog (Default)
echo   --no-seed, -n   Start with an empty catalog (no songs)
echo   --help, -h      Show this help message
exit /b 0

:after_args
if "%SEED_CHOICE%"=="" (
    echo Select Song Catalog Option:
    echo   [1] Seed songs from songs_links.csv (Default)
    echo   [2] Start with NO songs (Empty catalog)
    choice /c 12 /t 5 /d 1 /m "Choose [1/2] (auto-selects 1 in 5s): " >nul 2>&1
    if !errorlevel! equ 2 (
        set SEED_CHOICE=no-seed
    ) else (
        set SEED_CHOICE=seed
    )
)

if "%SEED_CHOICE%"=="no-seed" (
    set DELUX_NO_SEED=1
    echo  [MODE] Catalog: NO SONGS (Empty Catalog)
) else (
    set DELUX_NO_SEED=0
    echo  [MODE] Catalog: SEEDED SONGS (from songs_links.csv)
)
echo.

cd /d "%~dp0backend"

:: [1/5] Detect Python
set PYTHON_CMD=
for %%C in (python "py -3" py) do (
    if "!PYTHON_CMD!"=="" (
        %%~C --version >nul 2>&1
        if not errorlevel 1 set PYTHON_CMD=%%~C
    )
)

if "!PYTHON_CMD!"=="" (
    echo  [ERROR] Python not found. Please install Python 3.10+
    echo  Download: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%V in ('!PYTHON_CMD! --version 2^>^&1') do echo  [INFO] Using %%V

:: Create virtual environment if missing
if not exist "venv\Scripts\activate.bat" (
    echo  [1/5] Creating Python virtual environment...
    if exist "venv" rd /s /q "venv" >nul 2>&1
    !PYTHON_CMD! -m venv venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
) else (
    echo  [OK] [1/5] Virtual environment found.
)
echo.

:: [2/5] Activate venv
call venv\Scripts\activate.bat
echo  [OK] [2/5] Virtual environment activated.
echo.

:: Upgrade pip inside venv
python -m pip install --upgrade pip -q 2>nul

:: [3/5] Install / update dependencies
echo  [3/5] Installing / updating dependencies...
pip install -r requirements.txt -q --no-warn-script-location
if errorlevel 1 (
    echo  [WARN] Some packages may have failed. Continuing...
) else (
    echo  [OK] Core dependencies ready.
)
echo.

:: [4/5] Check & Update yt-dlp
echo  [4/5] Updating yt-dlp & extensions...
pip install "yt-dlp[default]" "yt-dlp-ejs" --pre -U -q --no-warn-script-location >nul 2>&1
for /f "tokens=*" %%V in ('python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2^>nul') do (
    echo  [OK] yt-dlp is at version %%V
)
echo.

:: System Dependency Checks
echo  [SYSTEM CHECKS]
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo  [WARN] FFmpeg not found. Audio mixing will use voice fallback.
    echo         Download: https://ffmpeg.org/download.html
) else (
    echo  [OK] FFmpeg found.
)

node --version >nul 2>&1
if errorlevel 1 (
    echo  [WARN] Node.js not found. YouTube extraction may fail for some music videos.
    echo         Download: https://nodejs.org/
) else (
    for /f "tokens=*" %%N in ('node --version 2^>nul') do echo  [OK] Node.js %%N found.
)

curl -s -m 2 http://localhost:11434/api/tags >nul 2>&1
if not errorlevel 1 (
    echo  [OK] Ollama AI is running (cinematic RJ generation active).
) else (
    echo  [INFO] Ollama is not running. Delux Radio will use built-in radio scripts.
    echo         (Optional: run 'ollama run llama3' for live AI voice scripts)
)
echo.

:: [5/5] Start server
echo  [5/5] Starting Delux Radio...
echo.
echo  ---------------------------------------------
echo  Main Player   -^>  http://localhost:8000
echo  Admin Panel   -^>  http://localhost:8000/admin.html
echo  Admin Login   -^>  admin / Awsedrft@123
echo  Public Tunnel -^>  tunnel\tunnel.sh (Git Bash / WSL)
echo  ---------------------------------------------
echo.
echo  Press Ctrl+C to stop the server.
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause