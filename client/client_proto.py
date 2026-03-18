#!/usr/bin/env python3
"""
PoC ana giriş noktası — Edge cihaz (client).
Platform: Pi-Star (agents.pistar). Konfig: .env (SERVER_ADDR, NODE_ID, AUTH_TOKEN veya NODE_PASSWORD).
"""

import logging
import os
import re
import signal
import sys
import threading
from typing import Dict

from client.agents.pistar import agent as pistar_agent
from client.agents.pistar import config as pistar_config
from client.core import identity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

_ENV_PATHS = [
    "/opt/mmdvm_link/.env",
    os.path.join(os.getcwd(), ".env"),
]


_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _load_env() -> Dict[str, str]:
    """İlk başarılı okunan .env dosyasından KEY=VALUE oku (export ve # yok say)."""
    out: Dict[str, str] = {}
    for path in _ENV_PATHS:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                tmp: Dict[str, str] = {}
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("export "):
                        line = line[7:].strip()
                    if "=" in line:
                        k, _, v = line.partition("=")
                        key = k.strip()
                        val = v.strip().strip("'\"")
                        if key:
                            tmp[key] = val
                out.update(tmp)
                break
        except OSError as e:
            logger.debug("load_env %s: %s", path, e)
    return out


def _is_pistar() -> bool:
    """Pi-Star ortamı: /var/log/pi-star varlığı ile basit tespit."""
    return os.path.isdir("/var/log/pi-star")


def _validate_node_id(node_id: str) -> None:
    node_id = (node_id or "").strip()
    if not node_id or not _NODE_ID_RE.fullmatch(node_id):
        logger.error(
            "Invalid NODE_ID %r. Expected non-empty and matching regex %s (only A-Z a-z 0-9 _ -; no slash).",
            node_id,
            _NODE_ID_RE.pattern,
        )
        sys.exit(1)


def main() -> None:
    env = _load_env()
    # systemd EnvironmentFile / real process environment must win over .env
    env.update(dict(os.environ))
    server_addr = env.get("SERVER_ADDR", "").strip()
    node_id = env.get("NODE_ID", "").strip()
    auth_token = env.get("AUTH_TOKEN", "").strip()
    node_password = env.get("NODE_PASSWORD", "").strip()

    if node_id:
        _validate_node_id(node_id)

    pre_signed = bool(node_id and (auth_token or node_password))
    if pre_signed:
        password = auth_token or node_password
    else:
        node_id = identity.get_node_id()
        password = node_password
        if not password:
            logger.error("NODE_PASSWORD veya (NODE_ID + AUTH_TOKEN) gerekli.")
            sys.exit(1)

    if not server_addr:
        logger.error("SERVER_ADDR gerekli.")
        sys.exit(1)

    hw_serial = identity.get_hw_serial()
    send_register = pre_signed and not pistar_config.is_registered()

    stop_ev = threading.Event()

    def on_signal(*_args: object) -> None:
        stop_ev.set()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    if _is_pistar():
        pistar_agent.run_pistar(
            server_addr,
            node_id,
            password,
            hw_serial=hw_serial,
            token=auth_token,
            send_register=send_register,
            stop_event=stop_ev,
        )
    else:
        logger.warning("Pi-Star ortamı tespit edilmedi (/var/log/pi-star); yine de pistar akışı çalıştırılıyor.")
        pistar_agent.run_pistar(
            server_addr,
            node_id,
            password,
            hw_serial=hw_serial,
            token=auth_token,
            send_register=send_register,
            stop_event=stop_ev,
        )


if __name__ == "__main__":
    main()
