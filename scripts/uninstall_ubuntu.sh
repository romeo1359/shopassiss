#!/usr/bin/env bash
set -euo pipefail
APP_NAME="telegram-shop-bot"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_NAME="${APP_NAME}.service"
if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo ./scripts/uninstall_ubuntu.sh"
  exit 1
fi
systemctl stop "$SERVICE_NAME" || true
systemctl disable "$SERVICE_NAME" || true
rm -f "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
read -r -p "Remove $INSTALL_DIR too? [y/N]: " ans
if [[ "$ans" =~ ^[Yy]$ ]]; then
  rm -rf "$INSTALL_DIR"
fi
echo "Uninstalled $SERVICE_NAME"
