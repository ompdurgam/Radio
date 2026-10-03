#!/usr/bin/env bash
# ==============================================================================
# Delux Radio — Universal Public Internet Tunnel
# Automatically detects system architecture, installs dependencies,
# and offers free-tier tunneling:
#   1. Cloudflare Tunnel (trycloudflare.com)
#   2. LocalTunnel (loca.lt)
#   3. Localhost.run (lhr.life)
# ==============================================================================

set -e

# Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
PURPLE='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"
mkdir -p "${BIN_DIR}"

PORT="${PORT:-8000}"
TUNNEL_PROVIDER=""
CUSTOM_TOKEN=""
CUSTOM_SUBDOMAIN=""

echo ""
echo -e "${CYAN}${BOLD}"
echo " ██████╗ ███████╗██╗     ██╗   ██╗██╗  ██╗   ████████╗██╗   ██╗███╗   ██╗███╗   ██╗███████╗██╗     "
echo " ██╔══██╗██╔════╝██║     ██║   ██║╚██╗██╔╝   ╚══██╔══╝██║   ██║████╗  ██║████╗  ██║██╔════╝██║     "
echo " ██║  ██║█████╗  ██║     ██║   ██║ ╚███╔╝       ██║   ██║   ██║██╔██╗ ██║██╔██╗ ██║█████╗  ██║     "
echo " ██║  ██║██╔══╝  ██║     ██║   ██║ ██╔██╗       ██║   ██║   ██║██║╚██╗██║██║╚██╗██║██╔══╝  ██║     "
echo " ██████╔╝███████╗███████╗╚██████╔╝██╔╝ ██╗      ██║   ╚██████╔╝██║ ╚████║██║ ╚████║███████╗███████╗"
echo " ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝      ╚═╝    ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═══╝╚══════╝╚══════╝"
echo -e "${NC}"
echo -e "${BOLD} DELUX RADIO -- Automated Public Tunnel Setup${NC}"
echo -e " ------------------------------------------------------------------------"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: Understand System Architecture
# ──────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}[STEP 1/3] Detecting System Architecture & Environment...${NC}"

RAW_OS="$(uname -s)"
OS="$(echo "$RAW_OS" | tr '[:upper:]' '[:lower:]')"
RAW_ARCH="$(uname -m)"

DISTRO_NAME=""
if [ -f /etc/os-release ]; then
    DISTRO_NAME=$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '"')
fi
[ -z "$DISTRO_NAME" ] && DISTRO_NAME="$RAW_OS"

# Normalize architecture to standard identifiers
case "$RAW_ARCH" in
    x86_64|amd64)
        NORM_ARCH="amd64"
        CF_ARCH="amd64"
        ;;
    aarch64|arm64)
        NORM_ARCH="arm64"
        CF_ARCH="arm64"
        ;;
    armv7l|armhf|arm)
        NORM_ARCH="armhf"
        CF_ARCH="arm"
        ;;
    i386|i686)
        NORM_ARCH="386"
        CF_ARCH="386"
        ;;
    *)
        NORM_ARCH="$RAW_ARCH"
        CF_ARCH="$RAW_ARCH"
        ;;
esac

echo -e "  Operating System : ${GREEN}${DISTRO_NAME}${NC}"
echo -e "  CPU Architecture : ${GREEN}${RAW_ARCH}${NC} (${NORM_ARCH})"
echo -e "  Target Port      : ${CYAN}${PORT}${NC}"
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: Verify & Install Necessary Dependencies
# ──────────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}[STEP 2/3] Checking & Installing Tunnel Dependencies...${NC}"

# Helper to auto-install missing packages as root or via sudo
apt_install() {
    if command -v apt-get >/dev/null 2>&1; then
        if [ "$EUID" -eq 0 ]; then
            apt-get update -qq && apt-get install -y "$@"
        elif command -v sudo >/dev/null 2>&1; then
            sudo apt-get update -qq && sudo apt-get install -y "$@"
        fi
    fi
}

# Check curl / wget
DOWNLOADER=""
if command -v curl >/dev/null 2>&1; then
    DOWNLOADER="curl"
    echo -e "  ${GREEN}[OK]${NC} curl is available"
elif command -v wget >/dev/null 2>&1; then
    DOWNLOADER="wget"
    echo -e "  ${GREEN}[OK]${NC} wget is available"
else
    echo -e "  ${YELLOW}[WARN]${NC} Neither curl nor wget found. Attempting install..."
    apt_install curl
    if command -v curl >/dev/null 2>&1; then
        DOWNLOADER="curl"
    else
        echo -e "  ${RED}[ERROR]${NC} Please install curl or wget."
        exit 1
    fi
fi

# Check SSH (Required for Localhost.run)
if command -v ssh >/dev/null 2>&1; then
    echo -e "  ${GREEN}[OK]${NC} OpenSSH client is available"
else
    echo -e "  ${YELLOW}[INFO]${NC} OpenSSH client missing. Installing openssh-client..."
    apt_install openssh-client
fi

# Check Node.js / NPX (For LocalTunnel)
HAS_NPX=false
if command -v npx >/dev/null 2>&1; then
    HAS_NPX=true
    echo -e "  ${GREEN}[OK]${NC} Node.js / npx is available ($(node --version 2>/dev/null || echo 'ready'))"
else
    echo -e "  ${YELLOW}[INFO]${NC} npx not found. Auto-installing nodejs & npm..."
    apt_install nodejs npm
    if command -v npx >/dev/null 2>&1; then
        HAS_NPX=true
        echo -e "  ${GREEN}[OK]${NC} Node.js / npx installed successfully"
    else
        echo -e "  ${YELLOW}[INFO]${NC} npx not available. Other tunnels (ngrok, Cloudflare, SSH) remain ready."
    fi
fi

# Check / Install ngrok
NGROK_BIN=""
if command -v ngrok >/dev/null 2>&1; then
    NGROK_BIN="$(command -v ngrok)"
    echo -e "  ${GREEN}[OK]${NC} ngrok binary found in PATH (${NGROK_BIN})"
elif [ -x "${BIN_DIR}/ngrok" ]; then
    NGROK_BIN="${BIN_DIR}/ngrok"
    echo -e "  ${GREEN}[OK]${NC} ngrok binary found in ${BIN_DIR}/ngrok"
else
    echo -e "  ${YELLOW}[INFO]${NC} Preparing ngrok for ${OS}-${NORM_ARCH}..."
    NGROK_DOWNLOAD_URL=""
    if [ "$OS" = "linux" ]; then
        NGROK_DOWNLOAD_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-${NORM_ARCH}.tgz"
    elif [ "$OS" = "darwin" ]; then
        NGROK_DOWNLOAD_URL="https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-darwin-${NORM_ARCH}.zip"
    fi

    if [ -n "$NGROK_DOWNLOAD_URL" ]; then
        echo -e "         Downloading ngrok from: ${CYAN}${NGROK_DOWNLOAD_URL}${NC} ..."
        if [ "$OS" = "darwin" ]; then
            curl -fsSL "$NGROK_DOWNLOAD_URL" -o "${BIN_DIR}/ngrok.zip" 2>/dev/null && unzip -q -o "${BIN_DIR}/ngrok.zip" -d "${BIN_DIR}" && rm -f "${BIN_DIR}/ngrok.zip" || true
        else
            curl -fsSL "$NGROK_DOWNLOAD_URL" 2>/dev/null | tar -xz -C "${BIN_DIR}" 2>/dev/null || true
        fi

        if [ -s "${BIN_DIR}/ngrok" ]; then
            chmod +x "${BIN_DIR}/ngrok"
            NGROK_BIN="${BIN_DIR}/ngrok"
            echo -e "  ${GREEN}[OK]${NC} ngrok installed successfully in ${BIN_DIR}/ngrok"
        else
            echo -e "  ${YELLOW}[WARN]${NC} Automatic ngrok download skipped."
        fi
    fi
fi

# Check / Install Cloudflare Tunnel (cloudflared) for system architecture
CLOUDFLARED_BIN=""
if command -v cloudflared >/dev/null 2>&1; then
    CLOUDFLARED_BIN="$(command -v cloudflared)"
    echo -e "  ${GREEN}[OK]${NC} Cloudflare tunnel binary found in PATH (${CLOUDFLARED_BIN})"
elif [ -x "${BIN_DIR}/cloudflared" ]; then
    CLOUDFLARED_BIN="${BIN_DIR}/cloudflared"
    echo -e "  ${GREEN}[OK]${NC} Cloudflare tunnel binary found in ${BIN_DIR}/cloudflared"
else
    echo -e "  ${YELLOW}[INFO]${NC} Preparing cloudflared for ${OS}-${CF_ARCH}..."
    CF_DOWNLOAD_URL=""
    if [ "$OS" = "linux" ]; then
        CF_DOWNLOAD_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}"
    elif [ "$OS" = "darwin" ]; then
        CF_DOWNLOAD_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-${CF_ARCH}.tgz"
    fi

    if [ -n "$CF_DOWNLOAD_URL" ]; then
        echo -e "         Downloading from: ${CYAN}${CF_DOWNLOAD_URL}${NC} ..."
        if [ "$DOWNLOADER" = "curl" ]; then
            curl -fsSL "$CF_DOWNLOAD_URL" -o "${BIN_DIR}/cloudflared" 2>/dev/null || true
        else
            wget -q "$CF_DOWNLOAD_URL" -O "${BIN_DIR}/cloudflared" 2>/dev/null || true
        fi

        if [ -s "${BIN_DIR}/cloudflared" ]; then
            chmod +x "${BIN_DIR}/cloudflared"
            CLOUDFLARED_BIN="${BIN_DIR}/cloudflared"
            echo -e "  ${GREEN}[OK]${NC} cloudflared installed successfully in ${BIN_DIR}/cloudflared"
        else
            echo -e "  ${YELLOW}[WARN]${NC} Automatic cloudflared download skipped. (Other tunnels ready)"
        fi
    fi
fi

# Check if Delux Radio server is active on target port
echo ""
echo -e "  Checking local Delux Radio server on port ${PORT}..."
if curl -s -m 2 "http://127.0.0.1:${PORT}/api/radio/state" >/dev/null 2>&1; then
    echo -e "  ${GREEN}[OK]${NC} Delux Radio is active and responding on http://127.0.0.1:${PORT}"
else
    echo -e "  ${YELLOW}[NOTICE]${NC} Delux Radio is not running on http://127.0.0.1:${PORT}."
    echo -e "           Run ${BOLD}./start.sh${NC} in another terminal so your radio plays live."
fi
echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Parse CLI flags (if any)
# ──────────────────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ngrok|-n)
            TUNNEL_PROVIDER="ngrok"
            shift
            ;;
        --cloudflare|--cf|-1)
            TUNNEL_PROVIDER="cloudflare"
            shift
            ;;
        --localtunnel|--lt|-2|-4)
            TUNNEL_PROVIDER="localtunnel"
            shift
            ;;
        --localhostrun|--lhr|-3)
            TUNNEL_PROVIDER="localhostrun"
            shift
            ;;
        --subdomain|-s)
            CUSTOM_SUBDOMAIN="$2"
            shift 2
            ;;
        --token|--authtoken|-t)
            CUSTOM_TOKEN="$2"
            shift 2
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: ./tunnel/tunnel.sh [OPTIONS]"
            echo ""
            echo "Tunnel Options:"
            echo "  --ngrok, -n           ngrok (ngrok-free.app)"
            echo "  --cloudflare, -1      Cloudflare Tunnel (trycloudflare.com)"
            echo "  --localtunnel, -2     LocalTunnel via npx (loca.lt)"
            echo "  --localhostrun, -3    Localhost.run SSH Tunnel (lhr.life)"
            echo ""
            echo "Configuration:"
            echo "  --port <PORT>, -p     Local port to forward (default: 8000)"
            echo "  --token <TOKEN>, -t   Provide account token (e.g. ngrok authtoken)"
            echo "  --subdomain <SUB>, -s Request custom subdomain / domain"
            echo "  --help, -h            Show this help message"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR] Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: Prompt user to choose the tunnel provider
# ──────────────────────────────────────────────────────────────────────────────
if [ -z "$TUNNEL_PROVIDER" ]; then
    echo -e "${BOLD}[STEP 3/3] Choose Tunnel Provider (All Free Tier):${NC}"
    echo -e "  ----------------------------------------------------------------------"
    echo -e "  ${CYAN}[1] ngrok${NC} ${GREEN}(Popular, Stable & Fast)${NC}"
    echo -e "      • Domain       : ${BOLD}*.ngrok-free.app${NC} (Free HTTPS)"
    echo -e "      • Features     : Web inspector (localhost:4040), custom domain support"
    echo ""
    echo -e "  ${CYAN}[2] Cloudflare Tunnel${NC} ${GREEN}(No Account Needed)${NC}"
    echo -e "      • Domain       : ${BOLD}*.trycloudflare.com${NC} (Free HTTPS)"
    echo -e "      • Features     : Automatic SSL, high speed, full WebSockets, zero config"
    echo ""
    echo -e "  ${CYAN}[3] LocalTunnel (loca.lt)${NC}"
    echo -e "      • Domain       : ${BOLD}*.loca.lt${NC} (Free HTTPS)"
    echo -e "      • Features     : Custom subdomain support, instant setup, no account needed"
    echo ""
    echo -e "  ${CYAN}[4] Localhost.run (SSH Tunnel)${NC}"
    echo -e "      • Domain       : ${BOLD}*.lhr.life${NC} (Free HTTPS)"
    echo -e "      • Features     : Pure SSH tunnel, auto-reconnect, zero downloads, no account needed"
    echo -e "  ----------------------------------------------------------------------"
    read -p "Select tunnel [1/2/3/4] (Default: 1): " user_choice
    echo ""

    case "$user_choice" in
        2)
            TUNNEL_PROVIDER="cloudflare"
            ;;
        3)
            TUNNEL_PROVIDER="localtunnel"
            ;;
        4)
            TUNNEL_PROVIDER="localhostrun"
            ;;
        *)
            TUNNEL_PROVIDER="ngrok"
            ;;
    esac
fi

# ──────────────────────────────────────────────────────────────────────────────
# EXECUTION HANDLERS
# ──────────────────────────────────────────────────────────────────────────────

# 1. ngrok Tunnel Handler
start_ngrok() {
    if [ -z "$NGROK_BIN" ] || [ ! -x "$NGROK_BIN" ]; then
        echo -e "${RED}[ERROR] ngrok binary is not available.${NC}"
        exit 1
    fi

    # Configure authtoken if passed via CLI
    if [ -n "$CUSTOM_TOKEN" ]; then
        "$NGROK_BIN" config add-authtoken "$CUSTOM_TOKEN" >/dev/null 2>&1 || true
    fi

    # Verify if ngrok already has an authtoken configured
    HAS_TOKEN=false
    if [ -f "$HOME/.config/ngrok/ngrok.yml" ] && grep -q "authtoken:" "$HOME/.config/ngrok/ngrok.yml" 2>/dev/null; then
        HAS_TOKEN=true
    fi

    if [ "$HAS_TOKEN" = false ]; then
        echo -e " ${YELLOW}[NOTICE]${NC} ngrok requires a free authtoken (one-time setup)."
        echo -e " 1. Get your free token: ${CYAN}https://dashboard.ngrok.com/get-started/your-authtoken${NC}"
        echo -e " ----------------------------------------------------------------------"
        read -p " Paste your ngrok authtoken here: " user_token
        echo ""
        if [ -n "$user_token" ]; then
            "$NGROK_BIN" config add-authtoken "$user_token"
        else
            echo -e " ${RED}[ERROR]${NC} ngrok requires an authtoken to start."
            echo "Tip: You can use Option 2 (Cloudflare Tunnel) if you don't want to sign up."
            exit 1
        fi
    fi

    echo -e " ----------------------------------------------------------------------"
    echo -e " ${GREEN}${BOLD}STARTING NGROK TUNNEL (Port ${PORT})${NC}"
    echo -e " Web Inspector & Status : ${CYAN}http://127.0.0.1:4040${NC}"
    echo -e " Share the public https://*.ngrok-free.app link with listeners live."
    echo -e " Press ${BOLD}Ctrl+C${NC} to stop the tunnel."
    echo -e " ----------------------------------------------------------------------"
    echo ""

    NGROK_ARGS=(http "$PORT")
    if [ -n "$CUSTOM_SUBDOMAIN" ]; then
        NGROK_ARGS+=(--domain "$CUSTOM_SUBDOMAIN")
    fi

    exec "$NGROK_BIN" "${NGROK_ARGS[@]}"
}

# 2. Cloudflare Tunnel Handler
start_cloudflare() {
    if [ -z "$CLOUDFLARED_BIN" ] || [ ! -x "$CLOUDFLARED_BIN" ]; then
        echo -e "${RED}[ERROR] cloudflared is not available.${NC}"
        echo "Please select another tunnel option (e.g. ngrok or Localhost.run)."
        exit 1
    fi

    echo -e " ----------------------------------------------------------------------"
    echo -e " ${GREEN}${BOLD}STARTING CLOUDFLARE TUNNEL (Port ${PORT})${NC}"
    echo -e " Look for the public ${CYAN}https://*.trycloudflare.com${NC} URL below!"
    echo -e " Share the link with listeners to tune into Delux Radio live."
    echo -e " Press ${BOLD}Ctrl+C${NC} to stop the tunnel."
    echo -e " ----------------------------------------------------------------------"
    echo ""

    if [ -n "$CUSTOM_TOKEN" ]; then
        exec "$CLOUDFLARED_BIN" tunnel run --token "$CUSTOM_TOKEN"
    else
        exec "$CLOUDFLARED_BIN" tunnel --url "http://localhost:${PORT}"
    fi
}

# 3. LocalTunnel Handler
start_localtunnel() {
    if ! command -v npx >/dev/null 2>&1; then
        echo -e "${RED}[ERROR] Node.js / npx is required to run LocalTunnel.${NC}"
        echo "Please select another tunnel option (e.g. ngrok or Cloudflare)."
        exit 1
    fi

    echo -e " ----------------------------------------------------------------------"
    echo -e " ${GREEN}${BOLD}STARTING LOCALTUNNEL (Port ${PORT})${NC}"
    echo -e " Look for the public ${CYAN}https://*.loca.lt${NC} URL below!"
    echo -e " Share the link with listeners to tune into Delux Radio live."
    echo -e " Press ${BOLD}Ctrl+C${NC} to stop the tunnel."
    echo -e " ----------------------------------------------------------------------"

    MY_IP=$(curl -s -m 3 https://loca.lt/mytunnelpassword 2>/dev/null || curl -s -m 3 https://ipv4.icanhazip.com 2>/dev/null || echo "")
    if [ -n "$MY_IP" ]; then
        echo -e " ${PURPLE}[INFO]${NC} If prompted for a tunnel password on loca.lt, enter your IP: ${BOLD}${CYAN}${MY_IP}${NC}"
    fi
    echo ""

    LT_ARGS=(--host "https://loca.lt" --port "$PORT")
    if [ -n "$CUSTOM_SUBDOMAIN" ]; then
        LT_ARGS+=(--subdomain "$CUSTOM_SUBDOMAIN")
    fi

    while true; do
        npx --yes localtunnel "${LT_ARGS[@]}" || true
        echo ""
        echo -e " ${YELLOW}[RECONNECT] LocalTunnel disconnected. Reconnecting in 3 seconds... (Press Ctrl+C to stop)${NC}"
        sleep 3
    done
}

# 4. Localhost.run Tunnel Handler
start_localhostrun() {
    echo -e " ----------------------------------------------------------------------"
    echo -e " ${GREEN}${BOLD}STARTING LOCALHOST.RUN TUNNEL (Port ${PORT})${NC}"
    echo -e " Look for the public ${CYAN}https://*.lhr.life${NC} URL below!"
    echo -e " Share the link with listeners to tune into Delux Radio live."
    echo -e " Press ${BOLD}Ctrl+C${NC} to stop the tunnel."
    echo -e " ----------------------------------------------------------------------"
    echo ""

    while true; do
        ssh \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -o ServerAliveInterval=15 \
            -o ServerAliveCountMax=3 \
            -R 80:localhost:"${PORT}" \
            nokey@localhost.run || true

        echo ""
        echo -e " ${YELLOW}[RECONNECT] Localhost.run disconnected. Reconnecting in 3 seconds... (Press Ctrl+C to stop)${NC}"
        sleep 3
    done
}

# Launch chosen tunnel
case "$TUNNEL_PROVIDER" in
    ngrok)
        start_ngrok
        ;;
    cloudflare)
        start_cloudflare
        ;;
    localtunnel)
        start_localtunnel
        ;;
    localhostrun)
        start_localhostrun
        ;;
    *)
        echo -e "${RED}[ERROR] Invalid tunnel selection.${NC}"
        exit 1
        ;;
esac


