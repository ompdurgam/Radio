# 🌐 Delux Radio — Public Internet Tunnels

Expose your local Delux Radio station to the internet so friends or listeners anywhere in the world can tune in, chat, and request songs live!

The script automatically detects your system architecture (Linux/macOS, x86_64, arm64, etc.), installs or verifies all dependencies, and gives you multiple completely free-tier options.

---

## 🔑 Permissions Setup (Linux / Ubuntu)

Before running the tunnel script for the first time, grant execution permissions:
```bash
chmod +x tunnel/tunnel.sh
```

---

## 🚀 Quick Start

Ensure Delux Radio is running locally:
```bash
./start.sh
```

In a new terminal window, run:
```bash
./tunnel/tunnel.sh
```

The script will:
1. Detect your OS and CPU architecture.
2. Check and prepare all required dependencies automatically.
3. Prompt you to select your preferred free-tier tunnel.

---

## 🛠 Available Free Tunnel Providers

| Provider | Domain | Protocol | Requirements |
|---|---|---|---|
| **ngrok** | `*.ngrok-free.app` | HTTPS + WSS | Auto-downloaded binary + free authtoken ([ngrok.com](https://dashboard.ngrok.com/signup)) |
| **Cloudflare Tunnel** | `*.trycloudflare.com` | HTTPS + WSS | Auto-downloads `cloudflared` (no account needed) |
| **LocalTunnel** | `*.loca.lt` | HTTPS + WSS | Uses `npx` (Node.js, no account needed) |
| **Localhost.run** | `*.lhr.life` | HTTPS + WSS | Uses native SSH (no account needed) |

---

## ⚡ Direct Command-Line Flags

```bash
# 1. ngrok (ngrok-free.app)
./tunnel/tunnel.sh --ngrok
# or: ./tunnel/tunnel.sh -n

# 2. Cloudflare Tunnel (trycloudflare.com)
./tunnel/tunnel.sh --cloudflare
# or: ./tunnel/tunnel.sh -1

# 3. LocalTunnel via npx (loca.lt)
./tunnel/tunnel.sh --localtunnel
# or: ./tunnel/tunnel.sh -2

# 4. Localhost.run SSH Tunnel (lhr.life)
./tunnel/tunnel.sh --localhostrun
# or: ./tunnel/tunnel.sh -3
```

### Custom Port / Token / Subdomain
```bash
# Provide ngrok authtoken directly:
./tunnel/tunnel.sh --ngrok --token <YOUR_AUTHTOKEN>

# Custom local port (default 8000):
./tunnel/tunnel.sh --ngrok --port 8000

# Custom domain (supported on ngrok and LocalTunnel):
./tunnel/tunnel.sh --ngrok --subdomain mydeluxradio.ngrok-free.app
./tunnel/tunnel.sh --localtunnel --subdomain mydeluxradio
```
