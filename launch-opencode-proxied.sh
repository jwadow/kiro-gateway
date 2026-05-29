#!/usr/bin/env bash
# launch-opencode-proxied.sh
# Starts forward_proxy.py then launches opencode with HTTP_PROXY wired.
# Works for opencode, kiro-cli, and owl-agent sessions.
#
# Usage:
#   ./launch-opencode-proxied.sh              # starts opencode
#   ./launch-opencode-proxied.sh kiro         # starts kiro-cli
#   ./launch-opencode-proxied.sh owl          # starts owl-agent run.sh
#   ./launch-opencode-proxied.sh -- myapp     # starts arbitrary command

set -euo pipefail

PROXY_DIR="$(cd "$(dirname "$0")" && pwd)"
PROXY_SCRIPT="$PROXY_DIR/forward_proxy.py"
PROXY_URL="http://127.0.0.1:60000"
PROXY_PID_FILE="/tmp/forward_proxy.pid"

# ── Start proxy if not already running ──────────────────────────────────────
if curl -sf "$PROXY_URL/_proxy/stats" >/dev/null 2>&1; then
  echo "[proxy] already running at $PROXY_URL"
else
  echo "[proxy] starting forward_proxy.py..."
  python3 "$PROXY_SCRIPT" &
  PROXY_PID=$!
  echo "$PROXY_PID" > "$PROXY_PID_FILE"

  # Wait up to 3s for it to bind
  for i in 1 2 3; do
    sleep 1
    if curl -sf "$PROXY_URL/_proxy/stats" >/dev/null 2>&1; then
      echo "[proxy] up (pid $PROXY_PID)"
      break
    fi
  done
fi

# ── Export proxy env vars ────────────────────────────────────────────────────
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"
export NO_PROXY="127.0.0.1,localhost"

# ── Launch target ────────────────────────────────────────────────────────────
TARGET="${1:-opencode}"

case "$TARGET" in
  opencode)
    echo "[launch] opencode with HTTP_PROXY=$PROXY_URL"
    exec opencode
    ;;
  kiro)
    echo "[launch] kiro-cli with HTTP_PROXY=$PROXY_URL"
    exec kiro
    ;;
  owl)
    echo "[launch] owl-agent with HTTP_PROXY=$PROXY_URL"
    source "$HOME/.owl-agent/env"
    exec "$HOME/.owl-agent/run.sh"
    ;;
  --)
    shift
    echo "[launch] $* with HTTP_PROXY=$PROXY_URL"
    exec "$@"
    ;;
  *)
    echo "[launch] $TARGET with HTTP_PROXY=$PROXY_URL"
    exec "$TARGET"
    ;;
esac
