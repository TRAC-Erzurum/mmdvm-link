# Hardware ID (Node ID) — tüm clientlarda ortak
"""
Raspberry Pi donanım seri numarası ve node_id üretimi.
Contract: node_id alfanumerik, tire, alt çizgi; slash yok.
"""

import re
import socket
import uuid
from pathlib import Path

_CPUINFO = Path("/proc/cpuinfo")
_SERIAL_RE = re.compile(r"^Serial\s*:\s*([0-9a-f]+)\s*$", re.MULTILINE)


def get_hw_serial() -> str:
    """Raspberry Pi donanım seri numarası (/proc/cpuinfo Serial). Pi değilse boş veya 'unknown'."""
    try:
        text = _CPUINFO.read_text(encoding="utf-8", errors="replace")
        m = _SERIAL_RE.search(text)
        if m:
            return m.group(1).strip()
    except (OSError, IOError, UnicodeDecodeError):
        pass
    return "unknown"


def get_node_id() -> str:
    """
    Broker-ACL modunda kullanılır: hw_serial'den türetilmiş tekil ID.
    Contract: alfanumerik, tire, alt çizgi; slash yok.
    """
    serial = get_hw_serial()
    if serial and serial != "unknown":
        return serial
    try:
        host = socket.gethostname() or "unknown"
        # Slash/boşluk kaldır; geçersiz karakterleri alt çizgi yap
        safe = re.sub(r"[^a-zA-Z0-9\-_]", "_", host)
        return safe[:32] if safe else "unknown"
    except Exception:
        return "unknown-" + str(uuid.uuid4()).replace("-", "")[:12]
