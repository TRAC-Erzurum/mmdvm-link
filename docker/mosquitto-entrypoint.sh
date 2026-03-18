#!/bin/sh
set -eu

# Single-container bootstrap for Mosquitto config stored on a shared volume.
# - Ensures /mosquitto/config/{mosquitto.conf,acl,passwd} exist (idempotent)
# - Validates LetsEncrypt cert/key at /etc/letsencrypt/live/${DOMAIN}/fullchain.pem + privkey.pem
# - Does NOT copy config elsewhere: Mosquitto reads live files from /mosquitto/config

DOMAIN="${DOMAIN:-}"
TLS_DOMAIN="${MQTT_TLS_DOMAIN:-${DOMAIN}}"

LE_LIVE_DIR="${LE_LIVE_DIR:-/etc/letsencrypt/live}"
CERTFILE="$LE_LIVE_DIR/$TLS_DOMAIN/fullchain.pem"
KEYFILE="$LE_LIVE_DIR/$TLS_DOMAIN/privkey.pem"

CONF_PATH="/mosquitto/config/mosquitto.conf"
ACL_PATH="/mosquitto/config/acl"
PASSWD_PATH="/mosquitto/config/passwd"

umask 077

mkdir -p /mosquitto/config /mosquitto/data

if [ -z "$TLS_DOMAIN" ]; then
  echo "ERROR: DOMAIN not set; required for TLS cert validation." >&2
  exit 1
fi

if [ ! -f "$CERTFILE" ] || [ ! -f "$KEYFILE" ]; then
  echo "ERROR: Missing TLS cert/key for domain '$TLS_DOMAIN'." >&2
  echo "Expected: $CERTFILE and $KEYFILE" >&2
  exit 1
fi

# External listener uses password auth; ensure passwd file exists (may be empty).
if [ ! -f "$PASSWD_PATH" ]; then
  : >"$PASSWD_PATH"
  chmod 600 "$PASSWD_PATH" || true
fi

if [ ! -s "$ACL_PATH" ]; then
  cat >"$ACL_PATH" <<'EOF'
pattern write nodes/telemetry/%u
pattern write nodes/status/%u
topic write nodes/register
pattern read nodes/cmd/%u
pattern read nodes/register/ack/%u
EOF
fi

if [ ! -s "$CONF_PATH" ]; then
  cat >"$CONF_PATH" <<EOF
per_listener_settings true

# Internal listener (no auth/acl). Network-only; do NOT publish to host.
listener 1883
protocol mqtt
allow_anonymous true

# External listener (TLS-only) published to host.
listener 8883
protocol mqtt

allow_anonymous false
password_file /mosquitto/config/passwd
acl_file /mosquitto/config/acl

certfile $CERTFILE
keyfile $KEYFILE
require_certificate false

persistence true
persistence_location /mosquitto/data/
autosave_interval 60

log_dest stdout
EOF
fi

exec mosquitto -c /mosquitto/config/mosquitto.conf

