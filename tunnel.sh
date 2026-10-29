#!/usr/bin/env bash
# ==============================================================================
# Delux Radio — Root Tunnel Launcher
# Delegates to tunnel/tunnel.sh with all passed arguments
# ==============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "${SCRIPT_DIR}/tunnel/tunnel.sh" "$@"
