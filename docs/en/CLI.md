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

  Found: kiro-cli (Linux/macOS)
  /home/you/.local/share/kiro-cli/data.sqlite3

  Use this credential source? [y/N]: y
  Proxy API key (clients use this to authenticate) [my-super-secret-password-123]:

  Configuration ready.
  Config saved to: /home/you/.config/kiro-gateway/.env
```

If no credential source is detected automatically, the wizard prompts you to choose manually:

```
  Choose your credential source:
  1) JSON credentials file  (recommended)
  2) Refresh token
  3) kiro-cli SQLite database  (AWS SSO)

  Enter choice (1-3):
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
| 3 | Current directory `.env` |
| 4 (lowest) | Saved config (`~/.config/kiro-gateway/.env`) |

---

## Managing Configuration

### Interactive config editor

```bash
kiro-gateway config
```

Opens an interactive numbered list of all configurable variables:

```
  Kiro Gateway — Configuration
  ──────────────────────────────────────────────────
  Config: /home/you/.config/kiro-gateway/.env

  Credentials
  [ 1] REFRESH_TOKEN                    (not set)
        Kiro refresh token (from IDE network traffic)
  [ 2] KIRO_CREDS_FILE                  /path/to/creds.json
        Path to Kiro credentials JSON file
  [ 3] KIRO_CLI_DB_FILE                 (not set)
        Path to kiro-cli SQLite database (AWS SSO)

  Server
  [ 4] PROXY_API_KEY                    my-super-****
        Client auth key (clients pass this as Bearer token)
  [ 5] SERVER_HOST                      0.0.0.0
        Bind address
  [ 6] SERVER_PORT                      8001
        Server port

  Network
  [ 7] VPN_PROXY_URL                    (not set)
        Proxy for Kiro API (GFW / corporate networks)
  [ 8] KIRO_REGION                      us-east-1
        AWS region

  Advanced
  [ 9] LOG_LEVEL                        INFO
        Log verbosity
  ...

  Enter number to edit, or q to quit:
```

Select a variable by number to edit it:

```
  PROXY_API_KEY — Client auth key (clients pass this as Bearer token)
  Current: my-super-****
  Allowed: (any string)
  Default: my-super-secret-password-123
  (Enter to keep current, '-' to clear)
  New value: my-new-secret-key
  Saved.
```

Changes are written to `~/.config/kiro-gateway/.env` immediately.

Enter `-` to clear a value. Press Enter without typing to keep the current value. Enter `q` to quit.

### Show config file path

```bash
kiro-gateway config --show-path
# /home/you/.config/kiro-gateway/.env
```

### Reset configuration

```bash
kiro-gateway config --reset
```

Prompts for confirmation, then deletes `~/.config/kiro-gateway/.env`.

---

## Configuration File

The config file lives at `~/.config/kiro-gateway/.env` (XDG Base Directory convention).

You can also edit it directly with any text editor:

```bash
nano ~/.config/kiro-gateway/.env
```

### All available options

```dotenv
# ── Credentials (choose one) ─────────────────────────────────────
# Option 1: JSON credentials file exported from Kiro IDE
KIRO_CREDS_FILE=/path/to/kiro-credentials.json

# Option 2: Refresh token captured from Kiro IDE network traffic
REFRESH_TOKEN=your_refresh_token_here

# Option 3: kiro-cli SQLite database (AWS SSO / Builder ID)
KIRO_CLI_DB_FILE=~/.local/share/kiro-cli/data.sqlite3

# ── Server ────────────────────────────────────────────────────────
PROXY_API_KEY=my-super-secret-password-123
SERVER_HOST=0.0.0.0
SERVER_PORT=8001

# ── Network ───────────────────────────────────────────────────────
# VPN_PROXY_URL=http://127.0.0.1:7890
# VPN_PROXY_URL=socks5://127.0.0.1:1080
KIRO_REGION=us-east-1

# ── Advanced ──────────────────────────────────────────────────────
LOG_LEVEL=INFO                        # TRACE/DEBUG/INFO/WARNING/ERROR/CRITICAL
FIRST_TOKEN_TIMEOUT=15
STREAMING_READ_TIMEOUT=300
FIRST_TOKEN_MAX_RETRIES=3
TRUNCATION_RECOVERY=true              # true/false
TOOL_DESCRIPTION_MAX_LENGTH=10000
DEBUG_MODE=off                        # off/errors/all
DEBUG_DIR=debug_logs
FAKE_REASONING=true                   # true/false
FAKE_REASONING_MAX_TOKENS=4000
FAKE_REASONING_HANDLING=as_reasoning_content  # as_reasoning_content/remove/pass/strip_tags
```

---

## Environment Variables

All options can also be set as environment variables. They take priority over the config file:

```bash
REFRESH_TOKEN="your_token" PROXY_API_KEY="secret" kiro-gateway
```

Useful for Docker, CI/CD, or temporary overrides without modifying the saved config.

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

If you use [kiro-cli](https://kiro.dev/cli/) with AWS SSO, the gateway auto-detects the database on first launch. You can also set it manually:

| Platform | Default path |
|----------|-------------|
| Linux / macOS | `~/.local/share/kiro-cli/data.sqlite3` |
| Amazon Q CLI | `~/.local/share/amazon-q/data.sqlite3` |
| macOS (alt) | `~/Library/Application Support/kiro-cli/data.sqlite3` |

---

## Command Reference

```
kiro-gateway [OPTIONS]
  -H, --host HOST     Server bind address (default: 0.0.0.0)
  -p, --port PORT     Server port (default: 8001)
  -v, --version       Show version and exit

kiro-gateway config
  (no flags)          Interactive configuration editor
  --show-path         Print config file path and exit
  --reset             Delete saved config file (with confirmation)
```

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

Your config file at `~/.config/kiro-gateway/.env` is **not** deleted automatically:

```bash
rm -rf ~/.config/kiro-gateway
```

---

## Troubleshooting

**"No credentials found" on every launch**

```bash
kiro-gateway config   # open editor and set credentials
```

**Check config file location**

```bash
kiro-gateway config --show-path
```

**Reset and reconfigure from scratch**

```bash
kiro-gateway config --reset
kiro-gateway          # wizard runs automatically on next launch
```
