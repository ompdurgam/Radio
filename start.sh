#!/usr/bin/env bash
# ==============================================================================
# Delux Radio — Ubuntu / Linux Startup Script
# ==============================================================================

set -e

# Terminal colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/backend"

echo ""
echo -e "${CYAN}${BOLD}"
echo " ██████╗ ███████╗██╗     ██╗   ██╗██╗  ██╗"
echo " ██╔══██╗██╔════╝██║     ██║   ██║╚██╗██╔╝"
echo " ██║  ██║█████╗  ██║     ██║   ██║ ╚███╔╝ "
echo " ██║  ██║██╔══╝  ██║     ██║   ██║ ██╔██╗ "
echo " ██████╔╝███████╗███████╗╚██████╔╝██╔╝ ██╗"
echo " ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝"
echo -e "${NC}"
echo -e "${BOLD} DELUX RADIO -- 90s Bollywood Radio Station${NC}"
echo -e " ---------------------------------------------"
# Catalog seeding options
SEED_CHOICE=""
for arg in "$@"; do
    case "$arg" in
        --seed|-s)
            SEED_CHOICE="seed"
            ;;
        --no-seed|--empty|-n)
            SEED_CHOICE="no-seed"
            ;;
        --help|-h)
            echo "Usage: ./start.sh [OPTIONS]"
            echo "  --seed, -s      Start and seed songs into catalog (Default)"
            echo "  --no-seed, -n   Start with an empty catalog (no songs)"
            echo "  --help, -h      Show this help message"
            exit 0
            ;;
    esac
done

if [ -z "$SEED_CHOICE" ]; then
    if [ -t 0 ]; then
        echo -e "${BOLD}Select Song Catalog Option:${NC}"
        echo -e "  ${CYAN}[1]${NC} Seed songs from songs_links.csv ${GREEN}(Default)${NC}"
        echo -e "  ${CYAN}[2]${NC} Start with NO songs (Empty catalog)"
        echo -n "Choose [1/2] (auto-selects 1 in 5s): "
        if read -t 5 user_choice; then
            echo ""
            if [ "$user_choice" = "2" ]; then
                SEED_CHOICE="no-seed"
            else
                SEED_CHOICE="seed"
            fi
        else
            echo ""
            SEED_CHOICE="seed"
        fi
    else
        SEED_CHOICE="seed"
    fi
fi

if [ "$SEED_CHOICE" = "no-seed" ]; then
    export DELUX_NO_SEED=1
    echo -e " ${YELLOW}[MODE]${NC} Catalog: ${BOLD}NO SONGS${NC} (Empty Catalog)"
else
    export DELUX_NO_SEED=0
    echo -e " ${GREEN}[MODE]${NC} Catalog: ${BOLD}SEEDED SONGS${NC} (from songs_links.csv)"
fi
echo ""

cd "${BACKEND_DIR}"

# Ensure executable permissions on all project scripts
chmod +x "${SCRIPT_DIR}/start.sh" "${SCRIPT_DIR}/tunnel.sh" "${SCRIPT_DIR}/tunnel/tunnel.sh" 2>/dev/null || true

# [0/5] Auto-install missing Ubuntu system packages (Python, FFmpeg, Node.js/npx, curl)
MISSING_PKGS=()
if ! command -v python3 >/dev/null 2>&1; then
    MISSING_PKGS+=("python3" "python3-venv" "python3-pip")
else
    python3 -c "import ensurepip" >/dev/null 2>&1 || MISSING_PKGS+=("python3-venv" "python3-pip")
fi
command -v ffmpeg >/dev/null 2>&1 || MISSING_PKGS+=("ffmpeg")
command -v curl >/dev/null 2>&1 || MISSING_PKGS+=("curl")
command -v node >/dev/null 2>&1 || MISSING_PKGS+=("nodejs" "npm")

if [ ${#MISSING_PKGS[@]} -gt 0 ] && command -v apt-get >/dev/null 2>&1; then
    echo -e " ${YELLOW}[AUTO-SETUP] Bare / fresh OS detected. Installing system dependencies: ${MISSING_PKGS[*]}...${NC}"
    if [ "$EUID" -eq 0 ]; then
        apt-get update -qq && apt-get install -y "${MISSING_PKGS[@]}"
    elif command -v sudo >/dev/null 2>&1; then
        sudo apt-get update -qq && sudo apt-get install -y "${MISSING_PKGS[@]}"
    fi
fi

# [1/5] Check Python 3
PYTHON_BIN=""
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        PYTHON_BIN="$cmd"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}[ERROR] Python 3 not found.${NC}"
    echo "Please install Python on Ubuntu with:"
    echo "    sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

PY_VER=$($PYTHON_BIN --version 2>&1)
echo -e " [INFO] Using ${GREEN}${PY_VER}${NC}"

# Check / create virtual environment
if [ ! -d "venv" ] || [ ! -f "venv/bin/activate" ]; then
    echo -e " [1/5] Creating Python virtual environment..."
    rm -rf venv
    if ! "$PYTHON_BIN" -m venv venv 2>/dev/null; then
        echo -e " ${YELLOW}[WARN] Default venv creation failed (missing ensurepip/python3-venv).${NC}"
        echo -e " Attempting bootstrap with --without-pip..."
        "$PYTHON_BIN" -m venv --without-pip venv
        
        # Bootstrap pip inside venv
        if command -v curl >/dev/null 2>&1; then
            curl -sS https://bootstrap.pypa.io/get-pip.py -o venv/get-pip.py
            venv/bin/python venv/get-pip.py -q
            rm -f venv/get-pip.py
        elif command -v wget >/dev/null 2>&1; then
            wget -qO venv/get-pip.py https://bootstrap.pypa.io/get-pip.py
            venv/bin/python venv/get-pip.py -q
            rm -f venv/get-pip.py
        else
            echo -e "${RED}[ERROR] Neither curl nor wget is available to bootstrap pip.${NC}"
            echo "Please run: sudo apt update && sudo apt install -y python3-venv python3-pip curl"
            exit 1
        fi
    fi
    echo -e " ${GREEN}[OK]${NC} Virtual environment created."
else
    echo -e " [1/5] Virtual environment found."
fi
echo ""

# [2/5] Activate venv
# shellcheck disable=SC1091
source venv/bin/activate
echo -e " ${GREEN}[OK]${NC} [2/5] Virtual environment activated."
echo ""

# Ensure pip is up-to-date inside venv
pip install --upgrade pip -q 2>/dev/null || true

# [3/5] Install dependencies
echo -e " [3/5] Installing / updating dependencies..."
if pip install -r requirements.txt -q --no-warn-script-location; then
    echo -e " ${GREEN}[OK]${NC} Core dependencies ready."
else
    echo -e " ${YELLOW}[WARN] Some packages may have failed. Continuing...${NC}"
fi
echo ""

# [4/5] Check & Update yt-dlp (essential for YouTube stream extraction)
echo -e " [4/5] Updating yt-dlp & extensions..."
if pip install "yt-dlp[default]" "yt-dlp-ejs" --pre -U -q --no-warn-script-location 2>/dev/null; then
    YTDLP_VER=$(python -c "import yt_dlp; print(yt_dlp.version.__version__)" 2>/dev/null || echo "installed")
    echo -e " ${GREEN}[OK]${NC} yt-dlp is at version ${CYAN}${YTDLP_VER}${NC}"
else
    echo -e " ${YELLOW}[WARN] yt-dlp update skipped. Using existing version.${NC}"
fi
echo ""

# System dependency checks for Ubuntu
echo -e " [SYSTEM CHECKS]"
if command -v ffmpeg >/dev/null 2>&1; then
    echo -e " ${GREEN}[OK]${NC} FFmpeg found."
else
    echo -e " ${YELLOW}[WARN] FFmpeg not found.${NC} Audio mixing & voice overlays will be limited."
    echo -e "        Install on Ubuntu with: ${BOLD}sudo apt install -y ffmpeg${NC}"
fi

if command -v node >/dev/null 2>&1; then
    NODE_VER=$(node --version)
    echo -e " ${GREEN}[OK]${NC} Node.js (${NODE_VER}) found. YouTube JS challenge solving enabled."
else
    echo -e " ${YELLOW}[WARN] Node.js not found.${NC} YouTube extraction may fail for some music videos."
    echo -e "        Install on Ubuntu with: ${BOLD}sudo apt install -y nodejs${NC}"
fi

# Check Ollama (optional)
if curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo -e " ${GREEN}[OK]${NC} Ollama AI is running (cinematic RJ generation active)."
else
    echo -e " ${YELLOW}[INFO] Ollama is not running.${NC} Delux Radio will use built-in radio scripts."
    echo -e "        (Optional: run 'ollama run llama3' for live AI voice scripts)"
fi
echo ""

# [5/5] Start server
echo -e " [5/5] Starting Delux Radio..."
echo ""
echo -e " ---------------------------------------------"
echo -e " Main Player   ->  ${CYAN}${BOLD}http://localhost:8000${NC}"
echo -e " Admin Panel   ->  ${CYAN}${BOLD}http://localhost:8000/admin.html${NC}"
echo -e " Admin Login   ->  ${BOLD}admin / Awsedrft@123${NC}"
echo -e " Public Tunnel ->  ${YELLOW}${BOLD}./tunnel/tunnel.sh${NC} (Share live online)"
echo -e " ---------------------------------------------"
echo ""
echo -e " Press ${BOLD}Ctrl+C${NC} to stop the server."
echo ""

exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
