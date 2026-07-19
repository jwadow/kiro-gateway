#!/usr/bin/env bash
set -euo pipefail

# Kiro Gateway - Install/Reinstall Script
# Installs as a user systemd service and (re)starts it.
# Requires: uv (https://docs.astral.sh/uv/)

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="kiro-gateway"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"
VENV_DIR="${REPO_DIR}/.venv"

echo "==> Kiro Gateway installer"
echo "    Repo: ${REPO_DIR}"

# Ensure systemd user directory exists
mkdir -p "$HOME/.config/systemd/user"

# Create/update virtualenv and install dependencies
echo "==> Installing dependencies with uv..."
uv venv "$VENV_DIR" --quiet
uv pip install --quiet -r "${REPO_DIR}/requirements.txt" -p "${VENV_DIR}/bin/python"

# Write systemd service unit
echo "==> Writing systemd service to ${SERVICE_FILE}"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Kiro Gateway
After=network.target

[Service]
WorkingDirectory=${REPO_DIR}
ExecStart=${VENV_DIR}/bin/python main.py
Restart=on-failure
RestartSec=5
Environment=PATH=${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
EOF

# Reload, enable, and restart
echo "==> Reloading systemd and restarting ${SERVICE_NAME}..."
systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}.service"
systemctl --user restart "${SERVICE_NAME}.service"

# Show status
echo "==> Done. Service status:"
systemctl --user status "${SERVICE_NAME}.service" --no-pager
