#!/bin/bash
# Docker entrypoint for kiro-gateway
#
# Solves the token refresh race condition (Issue #203):
# When both kiro-cli (host) and kiro-gateway (container) share the same SQLite DB,
# each token refresh invalidates the other's access token, causing 403 loops.
#
# Solution: Copy the seed database at startup so the container has its own
# independent token lifecycle. The host DB is mounted read-only as a seed.
#
# Kiro Hub integration adds three more startup steps:
#   - Decode a base64-encoded SQLite seed (KIRO_CLI_DB_SEED ending in .b64),
#     because text-only secret stores (e.g. Render secret files) cannot carry
#     a binary DB directly.
#   - Place an Enterprise AWS SSO device-registration file (KIRO_DEVICE_REG_SEED)
#     into ~/.aws/sso/cache/ where the gateway expects to find it by name.
#   - Copy a read-only KIRO_CREDS_FILE (e.g. Render /etc/secrets) to a WRITABLE
#     path so in-place token saves don't fail.

set -e

SEED_DB="${KIRO_CLI_DB_SEED:-}"
TARGET_DIR="/home/kiro/.local/share/kiro-cli"
TARGET_DB="${TARGET_DIR}/data.sqlite3"

# If a seed database path is provided, copy/decode it for independent token lifecycle
if [ -n "$SEED_DB" ] && [ -f "$SEED_DB" ]; then
    mkdir -p "$TARGET_DIR"
    case "$SEED_DB" in
        *.b64)
            # Seed is base64 text (binary DB can't ride a text secret file).
            base64 -d "$SEED_DB" > "$TARGET_DB"
            echo "[entrypoint] Decoded base64 seed DB from $SEED_DB → $TARGET_DB (independent token lifecycle)"
            ;;
        *)
            cp "$SEED_DB" "$TARGET_DB"
            echo "[entrypoint] Copied seed DB from $SEED_DB → $TARGET_DB (independent token lifecycle)"
            ;;
    esac
    chmod 600 "$TARGET_DB"

    # Point the gateway at the local copy (if not already set)
    if [ -z "$KIRO_CLI_DB_FILE" ]; then
        export KIRO_CLI_DB_FILE="$TARGET_DB"
    fi
fi

# Enterprise Kiro IDE (AWS SSO OIDC): place the device-registration file where
# the gateway looks for it — ~/.aws/sso/cache/{clientIdHash}.json.
#
# The target FILENAME comes from KIRO_DEVICE_REG_NAME (an env value), because a
# clientIdHash is hex and often starts with a digit — which Render rejects as a
# secret-file NAME. So the seed file itself has a safe fixed name, and the real
# {clientIdHash}.json name rides this env var. Falls back to the seed's basename
# for backward compatibility.
DEVICE_REG_SEED="${KIRO_DEVICE_REG_SEED:-}"
SSO_CACHE_DIR="/home/kiro/.aws/sso/cache"
if [ -n "$DEVICE_REG_SEED" ] && [ -f "$DEVICE_REG_SEED" ]; then
    mkdir -p "$SSO_CACHE_DIR"
    # basename() guards against path traversal in the provided name.
    DEVICE_REG_NAME="$(basename "${KIRO_DEVICE_REG_NAME:-$(basename "$DEVICE_REG_SEED")}")"
    DEVICE_REG_TARGET="${SSO_CACHE_DIR}/${DEVICE_REG_NAME}"
    cp "$DEVICE_REG_SEED" "$DEVICE_REG_TARGET"
    chmod 600 "$DEVICE_REG_TARGET"
    echo "[entrypoint] Placed Enterprise device-registration file at $DEVICE_REG_TARGET"
fi

# Read-only creds handling: when KIRO_CREDS_FILE points at a read-only mount
# (e.g. Render secret files at /etc/secrets), the gateway's in-place token save
# fails ([Errno 30] Read-only file system). Fix: copy the creds JSON to a
# WRITABLE path and re-point the gateway at the copy so in-session saves work.
CREDS_SRC="${KIRO_CREDS_FILE:-}"
CREDS_DIR="/home/kiro/.kiro-hub"
CREDS_TARGET="${CREDS_DIR}/kiro-auth-token.json"
if [ -n "$CREDS_SRC" ] && [ -f "$CREDS_SRC" ]; then
    mkdir -p "$CREDS_DIR"
    cp "$CREDS_SRC" "$CREDS_TARGET"
    chmod 600 "$CREDS_TARGET"
    export KIRO_CREDS_FILE="$CREDS_TARGET"
    echo "[entrypoint] Using writable creds copy at $CREDS_TARGET"
fi

# Run the main application
exec python main.py
