#!/usr/bin/env bash
set -euo pipefail
APP_NAME="telegram-shop-bot"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_NAME="${APP_NAME}.service"
USER_NAME="${SUDO_USER:-$USER}"
GROUP_NAME="$(id -gn "$USER_NAME")"
if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo ./scripts/update_ubuntu.sh"
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude '.env' --exclude 'bot_database.db' --exclude 'uploads' --exclude 'backups' \
  "$PROJECT_ROOT/" "$INSTALL_DIR/"
chown -R "$USER_NAME:$GROUP_NAME" "$INSTALL_DIR"
sudo -u "$USER_NAME" "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
systemctl restart "$SERVICE_NAME"
echo "Updated and restarted $SERVICE_NAME"
