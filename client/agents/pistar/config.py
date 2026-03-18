# Pi-Star özel ayarlar: log yolları, rpi-rw/ro komutları, venv, .registered flag

import os
import time
from typing import Optional

LOG_GLOB = "/var/log/pi-star/MMDVM-*.log"
RPI_RW_CMD = "rpi-rw"
RPI_RO_CMD = "rpi-ro"
VENV_ROOT = "/opt/mmdvm_link/"
REGISTERED_FLAG = "/opt/mmdvm_link/.registered"
LAST_REGISTER_ATTEMPT_FILE = "/opt/mmdvm_link/.last_register_attempt"
REGISTER_ATTEMPT_MIN_INTERVAL_S = 6 * 60 * 60


def is_registered() -> bool:
    """Yerel .registered flag dosyası varsa True (register atlanır)."""
    return os.path.isfile(REGISTERED_FLAG)


def can_write_registered_flag() -> bool:
    parent = os.path.dirname(REGISTERED_FLAG) or "/"
    if os.path.exists(REGISTERED_FLAG):
        return os.access(REGISTERED_FLAG, os.W_OK)
    return os.access(parent, os.W_OK)


def set_registered() -> bool:
    """Ack sonrası .registered flag dosyasını oluştur. Başarılı ise True."""
    try:
        open(REGISTERED_FLAG, "a").close()
        return True
    except OSError:
        return False


def _read_int_file(path: str) -> int:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return int((f.read() or "").strip() or "0")
    except OSError:
        return 0
    except ValueError:
        return 0


def should_skip_register_attempt(now_epoch_s: Optional[int] = None) -> bool:
    now = int(time.time()) if now_epoch_s is None else int(now_epoch_s)
    last = _read_int_file(LAST_REGISTER_ATTEMPT_FILE)
    if last <= 0:
        return False
    return (now - last) < REGISTER_ATTEMPT_MIN_INTERVAL_S


def record_register_attempt(now_epoch_s: Optional[int] = None) -> None:
    now = int(time.time()) if now_epoch_s is None else int(now_epoch_s)
    try:
        with open(LAST_REGISTER_ATTEMPT_FILE, "w", encoding="utf-8") as f:
            f.write(str(now))
    except OSError:
        pass
