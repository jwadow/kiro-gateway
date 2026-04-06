# Kiro Gateway — CLI Tool Guide

This guide covers installing and using Kiro Gateway as a global CLI tool via `uv tool install`.

---

## Installation

```bash
uv tool install git+https://github.com/jwadow/kiro-gateway.git
```

After installation, the `kiro-gateway` command is available globally.

---

## First-Time Setup

On first launch, if no credentials are configured, the gateway starts an interactive setup wizard automatically:

```
$ kiro-gateway

  👻 Kiro Gateway — First-time Setup
  ────────────────────────────────────────────
  No credentials found. Let's set them up.

  Choose your credential source:
  1) JSON credentials file  (recommended)
  2) Refresh token
  3) kiro-cli SQLite database  (AWS SSO)

  Enter choice (1-3): 1
  Path to your Kiro credentials JSON file: /path/to/kiro-credentials.json
  Proxy API key (clients use this to authenticate) [my-super-secret-password-123]:

  Configuration ready.
  Config saved to: /Users/you/.config/kiro-gateway/.env
```

The wizard saves your configuration to `~/.config/kiro-gateway/.env`. You only need to run it once.

---

## Starting the Server

```bash
# Start with defaults (0.0.0.0:8001)
kiro-gateway

# Custom port
kiro-gateway --port 9000

# Local connections only
kiro-gateway --host 127.0.0.1

# Short form
kiro-gateway -H 0.0.0.0 -p 8080
```

### Configuration Priority

Settings are resolved in this order (highest wins):

| Priority | Source |
|----------|--------|
| 1 (highest) | CLI arguments (`--host`, `--port`) |
| 2 | Environment variables (`SERVER_HOST`, `SERVER_PORT`) |
| 3 (lowest) | Saved config (`~/.config/kiro-gateway/.env`) |

---

## Managing Configuration

### View current configuration

```bash
kiro-gateway config
```

Output example:

```
  Kiro Gateway — Current Configuration
  ────────────────────────────────────────────
  Config file: /Users/you/.config/kiro-gateway/.env

  File exists
  
  REFRESH_TOKEN    = (not set)
  KIRO_CREDS_FILE  = /path/to/kiro-credentials.json
  KIRO_CLI_DB_FILE = (not set)
  PROXY_API_KEY    = my-super-****
  SERVER_HOST      = (not set)
  SERVER_PORT      = (not set)
```

Sensitive values (`REFRESH_TOKEN`, `PROXY_API_KEY`) are partially masked.

### Re-run setup wizard

```bash
kiro-gateway config --edit
```

Launches the interactive wizard again to update your credentials or API key.

### Show config file path

```bash
kiro-gateway config --show-path
# /Users/you/.config/kiro-gateway/.env
```

### Reset configuration

```bash
kiro-gateway config --reset
```

Prompts for confirmation, then deletes `~/.config/kiro-gateway/.env`.

---

## Configuration File

The config file lives at `~/.config/kiro-gateway/.env` (XDG Base Directory convention).

You can edit it directly with any text editor:

```bash
# macOS / Linux
nano ~/.config/kiro-gateway/.env
```

### Available options

```dotenv
# ── Credentials (choose one) ─────────────────────────────────────
# Option 1: JSON credentials file exported from Kiro IDE
KIRO_CREDS_FILE=/path/to/kiro-credentials.json

# Option 2: Refresh token captured from Kiro IDE network traffic
REFRESH_TOKEN=your_refresh_token_here

# Option 3: kiro-cli SQLite database (AWS SSO / Builder ID)
KIRO_CLI_DB_FILE=~/.local/share/kiro-cli/data.sqlite3

# ── Proxy API key ─────────────────────────────────────────────────
# Clients must pass this as the Authorization Bearer token
PROXY_API_KEY=my-super-secret-password-123

# ── Server ────────────────────────────────────────────────────────
SERVER_HOST=0.0.0.0
SERVER_PORT=8001

# ── Network ───────────────────────────────────────────────────────
# Optional: route Kiro API traffic through a proxy (GFW, corporate)
# VPN_PROXY_URL=http://127.0.0.1:7890
# VPN_PROXY_URL=socks5://127.0.0.1:1080

# ── AWS region ────────────────────────────────────────────────────
# KIRO_REGION=us-east-1
```

---

## Environment Variables

All options can also be set as environment variables. They take priority over the config file:

```bash
REFRESH_TOKEN="your_token" PROXY_API_KEY="secret" kiro-gateway
```

This is useful for Docker, CI/CD, or temporary overrides without modifying the saved config.

---

## Obtaining Credentials

### Option 1 — JSON credentials file (recommended)

1. Open Kiro IDE
2. Open DevTools → Network tab
3. Find a request to `kiro.dev` and copy the credentials JSON
4. Save to a file and set `KIRO_CREDS_FILE` to its path

### Option 2 — Refresh token

1. Open Kiro IDE
2. Open DevTools → Network tab → filter by `refreshToken`
3. Copy the `refreshToken` value from the request body
4. Set as `REFRESH_TOKEN`

### Option 3 — kiro-cli SQLite database

If you use [kiro-cli](https://kiro.dev/cli/) with AWS SSO:

| Platform | Default path |
|----------|-------------|
| Linux / macOS | `~/.local/share/kiro-cli/data.sqlite3` |
| Amazon Q CLI | `~/.local/share/amazon-q/data.sqlite3` |
| Windows | `%APPDATA%\kiro-cli\data.sqlite3` |

Set `KIRO_CLI_DB_FILE` to the appropriate path.

---

## Upgrading

```bash
uv tool upgrade kiro-gateway
```

---

## Uninstalling

```bash
uv tool uninstall kiro-gateway
```

Your config file at `~/.config/kiro-gateway/.env` is **not** deleted automatically. Remove it manually if needed:

```bash
rm -rf ~/.config/kiro-gateway
```

---

## Troubleshooting

### "No credentials found" on every launch

The wizard did not save, or the config file was deleted. Run:

```bash
kiro-gateway config --edit
```

### Config file location

```bash
kiro-gateway config --show-path
```

### Check what values are active

```bash
kiro-gateway config
```

### Reset and reconfigure from scratch

```bash
kiro-gateway config --reset
kiro-gateway config --edit
```
