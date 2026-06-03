#!/bin/sh
# Copy the mounted (read-only) kiro-cli database to a local writable path
# so the gateway has its own independent token lifecycle.

SRC="/mnt/kiro-cli-seed/data.sqlite3"
DEST_DIR="/home/kiro/.local/share/kiro-cli"
DEST="$DEST_DIR/data.sqlite3"

if [ -f "$SRC" ]; then
    mkdir -p "$DEST_DIR"
    cp "$SRC" "$DEST"
    echo "Copied seed database to $DEST"
fi

exec "$@"
