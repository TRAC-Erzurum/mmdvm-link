#!/bin/bash
# Pi-Star pre-signed bootstrap (zero-config).
# Sunucu tarafından üretildiğinde SERVER_ADDR, NODE_ID, AUTH_TOKEN script içinde gömülü olur.
# Çalıştırma: sudo ./install.sh (root gerekli).

set -euo pipefail
IFS=$'\n\t'

# --- Pre-configured (sunucu üretiminde bu değerler doldurulur) ---
SERVER_ADDR="${SERVER_ADDR:-}"
NODE_ID="${NODE_ID:-}"
AUTH_TOKEN="${AUTH_TOKEN:-}"

if [ -z "$SERVER_ADDR" ] || [ -z "$NODE_ID" ] || [ -z "$AUTH_TOKEN" ]; then
  echo "Hata: SERVER_ADDR, NODE_ID ve AUTH_TOKEN gerekli. Script sunucu tarafından üretilmiş olmalı." >&2
  exit 1
fi

case "$SERVER_ADDR$NODE_ID$AUTH_TOKEN" in
  *$'\n'*|*$'\r'*)
    echo "Hata: SERVER_ADDR/NODE_ID/AUTH_TOKEN icinde yeni satir (LF/CR) olamaz." >&2
    exit 1
    ;;
esac

if [ "$(id -u)" -ne 0 ]; then
  echo "Root (sudo) gerekli." >&2
  exit 1
fi

echo "rpi-rw..."
if ! command -v rpi-rw >/dev/null 2>&1; then
  echo "Hata: rpi-rw bulunamadi. Pi-Star ortami gerekli." >&2
  exit 1
fi
rpi-rw

ROOT="/opt/mmdvm_link"
mkdir -p "$ROOT"
chmod 700 "$ROOT"
chown root:root "$ROOT"

# Client kodu: script ile aynı dağıtımda client/ dizini varsa kopyala
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
if [ -d "$REPO_ROOT/client" ]; then
  echo "Client kodu kopyalanıyor..."
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$REPO_ROOT/client/" "$ROOT/client/"
  else
    rm -rf "$ROOT/client"
    cp -a "$REPO_ROOT/client" "$ROOT/"
  fi
else
  echo "Uyarı: client/ dizini bulunamadı. Dağıtımda client ağacı olmalı." >&2
fi

if [ ! -f "$ROOT/client/client_proto.py" ]; then
  echo "Hata: client kopyalama basarisiz. '$ROOT/client/client_proto.py' bulunamadi." >&2
  exit 1
fi

# venv
if [ ! -d "$ROOT/venv" ]; then
  python3 -m venv "$ROOT/venv"
fi
"$ROOT/venv/bin/pip" install --upgrade pip
if [ ! -f "$REPO_ROOT/requirements.txt" ]; then
  echo "Hata: requirements.txt bulunamadi: $REPO_ROOT/requirements.txt" >&2
  exit 1
fi
"$ROOT/venv/bin/pip" install -r "$REPO_ROOT/requirements.txt"

# .env
cat > "$ROOT/.env" << EOF
SERVER_ADDR=$SERVER_ADDR
NODE_ID=$NODE_ID
AUTH_TOKEN=$AUTH_TOKEN
EOF
chmod 600 "$ROOT/.env"
chown root:root "$ROOT/.env"

# systemd
cat > /etc/systemd/system/mmdvm-link.service << 'SVCEOF'
[Unit]
Description=MMDVM-Link Edge Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/mmdvm_link
EnvironmentFile=/opt/mmdvm_link/.env
ExecStart=/opt/mmdvm_link/venv/bin/python -m client.client_proto
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable --now mmdvm-link.service

echo "rpi-ro..."
if ! rpi-ro; then
  echo "Uyarı: rpi-ro başarısız. Öneri: sudo reboot" >&2
fi

echo "Kurulum tamamlandı."
