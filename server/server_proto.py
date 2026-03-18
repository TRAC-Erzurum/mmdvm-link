#!/usr/bin/env python3
# ruff: noqa: E402
"""
Central Controller (CLI server) — Merkezi Yönetim sunucusu.
Loads .env from server dir, starts MQTT client, runs CLI loop.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Use server dir for .env; add repo root so "server" package can be imported
SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(SERVER_DIR / ".env")

from server.core.state import State
from server.core.mqtt_handler import MQTTHandler
from server.core.cli import run as cli_run

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v or not v.strip():
        logger.error("Missing required env: %s", name)
        sys.exit(1)
    return v.strip()


def _require_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    raw = raw.strip()
    try:
        return int(raw)
    except ValueError:
        logger.error("Invalid integer value for env %s: %r", name, raw)
        sys.exit(1)


def main() -> None:
    mqtt_broker = _require_env("MQTT_BROKER")
    mqtt_user = _require_env("MQTT_USER")
    mqtt_password = _require_env("MQTT_PASSWORD")
    broker_password_file = os.environ.get("BROKER_PASSWORD_FILE")
    if broker_password_file is not None:
        broker_password_file = broker_password_file.strip() or None
    server_addr = _require_env("SERVER_ADDR")
    mqtt_port = _require_int_env("MQTT_PORT", 1883)

    persist_raw = (os.environ.get("PERSIST_BINDINGS", "1") or "").strip().lower()
    persist_bindings = persist_raw not in {"0", "false", "no", "off"}
    if persist_bindings:
        bindings_path_env = os.environ.get("BINDINGS_PATH")
        if bindings_path_env is not None:
            bindings_path_env = bindings_path_env.strip() or None
        bindings_path = Path(bindings_path_env) if bindings_path_env else (SERVER_DIR / "bindings.json")
        state = State(bindings_path=str(bindings_path))
    else:
        state = State(bindings_path=None)
    mqtt_handler = MQTTHandler(
        state=state,
        broker=mqtt_broker,
        port=mqtt_port,
        username=mqtt_user,
        password=mqtt_password,
    )
    mqtt_handler.start()
    try:
        cli_run(
            state,
            mqtt_handler,
            output_dir=str(SERVER_DIR),
            server_addr=server_addr,
            broker_password_file=broker_password_file,
        )
    finally:
        mqtt_handler.stop()


if __name__ == "__main__":
    main()
