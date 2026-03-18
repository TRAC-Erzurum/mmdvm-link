# Pi-Star özel client mantığı: log tail → telemetry, cmd → console, presence

import glob
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from client.agents.pistar import config as pistar_config
from client.core.mqtt_client import MQTTLinkClient

logger = logging.getLogger(__name__)


def _latest_log_path() -> Optional[str]:
    """config.LOG_GLOB ile en son mtime'a sahip MMDVM-*.log dosyasını döndür."""
    pattern = pistar_config.LOG_GLOB
    paths = glob.glob(pattern)
    if not paths:
        return None
    best_path: Optional[str] = None
    best_mtime = 0.0
    for p in paths:
        try:
            m = os.path.getmtime(p)
            if m > best_mtime:
                best_mtime = m
                best_path = p
        except OSError:
            continue
    return best_path


def _cmd_callback_to_console(payload: str) -> None:
    """nodes/cmd/{node_id} gelen düz metni console'a yaz."""
    if os.getenv("YTC_CMD_PRINT", "1").strip().lower() not in {"0", "false", "no", "off"}:
        print(f"[cmd] {payload}", flush=True)
    snippet = (payload or "")[:200]
    logger.info("cmd received len=%s head=%r", len(payload or ""), snippet)


def run_telemetry_tail(
    mqtt_client: MQTTLinkClient,
    node_id: str,
    *,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    MMDVM-*.log glob → en güncel dosyayı tail et → her satırı JSON ile nodes/telemetry/{node_id} yayınla.
    Contract: {"log_line": "...", "timestamp": "ISO8601"}, isteğe bağlı "source".
    """
    include_source = os.getenv("YTC_TELEMETRY_INCLUDE_SOURCE", "").strip().lower() in {"1", "true", "yes", "on"}
    poll_interval = 1.0
    current_path: Optional[str] = None
    current_fp = None
    current_inode: Optional[int] = None

    def close_current() -> None:
        nonlocal current_fp
        if current_fp:
            try:
                current_fp.close()
            except Exception:
                pass
            current_fp = None

    try:
        while stop_event is None or not stop_event.is_set():
            path = _latest_log_path()
            if not path:
                time.sleep(poll_interval)
                continue
            try:
                st = os.stat(path)
                inode = st.st_ino
            except OSError:
                time.sleep(poll_interval)
                continue
            if path != current_path or inode != current_inode:
                close_current()
                current_path = path
                current_inode = inode
                try:
                    current_fp = open(path, "r", encoding="utf-8", errors="replace")
                    current_fp.seek(0, 2)
                except OSError as e:
                    logger.debug("open %s: %s", path, e)
                    current_path = None
                    current_inode = None
                    time.sleep(poll_interval)
                    continue
            if not current_fp:
                time.sleep(poll_interval)
                continue
            try:
                line = current_fp.readline()
            except OSError:
                close_current()
                current_path = None
                current_inode = None
                time.sleep(poll_interval)
                continue
            if line:
                line = line.rstrip("\n\r")
                ts = datetime.now(timezone.utc).isoformat()
                payload = {
                    "log_line": line,
                    "timestamp": ts,
                }
                if include_source:
                    source_name = os.path.basename(path)
                    payload["source"] = source_name
                mqtt_client.publish_telemetry(node_id, payload)
            else:
                time.sleep(poll_interval)
        close_current()
    except Exception as e:
        logger.exception("telemetry tail: %s", e)
    finally:
        close_current()


def run_pistar(
    server_addr: str,
    node_id: str,
    password: str,
    *,
    hw_serial: str = "",
    token: str = "",
    send_register: bool = False,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """
    Pi-Star akışı: connect, (isteğe bağlı register), status online, subscribe cmd, telemetry tail.
    send_register=True ve .registered yoksa nodes/register gönderir ve .registered oluşturur.
    """
    mqtt_client = MQTTLinkClient()
    mqtt_client.connect(server_addr, node_id, password)

    if send_register and token and hw_serial and not pistar_config.is_registered():
        ro_mode = not pistar_config.can_write_registered_flag()
        if ro_mode and pistar_config.should_skip_register_attempt():
            logger.info("register skipped (rate limited in RO mode)")
        else:
            if ro_mode:
                pistar_config.record_register_attempt()
            mqtt_client.subscribe_register_ack(node_id)
            mqtt_client.publish_register(node_id, token, hw_serial)
            if mqtt_client.wait_for_register_ack(10.0):
                if not pistar_config.set_registered() and ro_mode:
                    pistar_config.record_register_attempt()
            else:
                logger.warning("register ack not received (timeout)")

    mqtt_client.publish_status(node_id, "online")
    mqtt_client.subscribe_commands(_cmd_callback_to_console)

    ev = stop_event or threading.Event()
    tail_thread = threading.Thread(
        target=run_telemetry_tail,
        args=(mqtt_client, node_id),
        kwargs={"stop_event": ev},
        daemon=True,
    )
    tail_thread.start()
    try:
        ev.wait()
    except KeyboardInterrupt:
        pass
    ev.set()
    mqtt_client.stop_loop()
    tail_thread.join(timeout=5)
