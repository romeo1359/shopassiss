#!/usr/bin/env bash
set -euo pipefail

APP_NAME="telegram-shop-bot"
INSTALL_DIR="/opt/${APP_NAME}"
SERVICE_NAME="${APP_NAME}.service"
PYTHON_BIN="python3"
USER_NAME="${SUDO_USER:-$USER}"
GROUP_NAME="$(id -gn "$USER_NAME")"

if [[ $EUID -ne 0 ]]; then
  echo "Please run with sudo: sudo ./scripts/install_ubuntu.sh"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "==> Updating apt cache"
apt-get update -y

echo "==> Installing required packages"
apt-get install -y python3 python3-venv python3-pip git

echo "==> Creating install directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'uploads' \
  --exclude 'backups' \
  "$PROJECT_ROOT/" "$INSTALL_DIR/"

mkdir -p "$INSTALL_DIR/uploads" "$INSTALL_DIR/backups"
chown -R "$USER_NAME:$GROUP_NAME" "$INSTALL_DIR"

echo "==> Setting up virtual environment"
sudo -u "$USER_NAME" "$PYTHON_BIN" -m venv "$INSTALL_DIR/.venv"
sudo -u "$USER_NAME" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip wheel
sudo -u "$USER_NAME" "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

ENV_FILE="$INSTALL_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "==> Creating .env file"
  read -r -p "Enter BOT_TOKEN: " BOT_TOKEN
  read -r -p "Enter ADMIN_ID: " ADMIN_ID
  read -r -p "Enter EMAIL_USER (optional): " EMAIL_USER
  read -r -s -p "Enter EMAIL_PASS (optional): " EMAIL_PASS
  echo
  read -r -p "Enter ENCRYPTION_KEY (optional, press Enter to auto-generate): " ENCRYPTION_KEY
  if [[ -z "$ENCRYPTION_KEY" ]]; then
    ENCRYPTION_KEY=$(sudo -u "$USER_NAME" "$INSTALL_DIR/.venv/bin/python" - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
)
  fi
  cat > "$ENV_FILE" <<EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
EMAIL_USER=$EMAIL_USER
EMAIL_PASS=$EMAIL_PASS
ENCRYPTION_KEY=$ENCRYPTION_KEY
UPLOADS_DIR=uploads
BACKUP_DIR=backups
EOF
  chown "$USER_NAME:$GROUP_NAME" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

cat > "/etc/systemd/system/$SERVICE_NAME" <<EOF
[Unit]
Description=Telegram Shop Bot
After=network.target

[Service]
Type=simple
User=$USER_NAME
Group=$GROUP_NAME
WorkingDirectory=$INSTALL_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$INSTALL_DIR/.venv/bin/python $INSTALL_DIR/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "==> Reloading systemd"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo
systemctl --no-pager --full status "$SERVICE_NAME" || true
echo
echo "Installed successfully. Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -f"
echo "  sudo systemctl restart $SERVICE_NAME"
