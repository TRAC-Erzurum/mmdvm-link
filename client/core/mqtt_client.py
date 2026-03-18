# Standart MQTT kontratı (Pub/Sub) — tüm clientlarda ortak
"""
Central Controller ↔ Client MQTT Contract (plandaki §13).
connect, LWT, publish_register, publish_telemetry, publish_status, subscribe_commands.
"""

import json
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

DEFAULT_PORT = 1883

TOPIC_TELEMETRY = "nodes/telemetry/{}"
TOPIC_STATUS = "nodes/status/{}"
TOPIC_CMD = "nodes/cmd/{}"
TOPIC_REGISTER = "nodes/register"
TOPIC_REGISTER_ACK = "nodes/register/ack/{}"


def parse_server_addr(server_addr: str) -> Tuple[str, int]:
    """SERVER_ADDR → (host, port). ':' yoksa port 1883."""
    if ":" in server_addr:
        parts = server_addr.split(":", 1)
        host = parts[0].strip()
        try:
            port = int(parts[1].strip())
        except ValueError:
            port = DEFAULT_PORT
        return host, port
    return server_addr.strip(), DEFAULT_PORT


class MQTTLinkClient:
    """MQTT client: connect (username=node_id, password), LWT, telemetry, status, register, cmd subscribe."""

    def __init__(self) -> None:
        self._client: Optional[mqtt.Client] = None
        self._node_id: Optional[str] = None
        self._connected = False
        self._register_ack_event = threading.Event()
        self._register_ack_ok: Optional[bool] = None
        self._cmd_callback: Optional[Callable[[str], None]] = None

    def _wait_connected(self, timeout_s: float = 10.0) -> bool:
        """_connected True olana kadar (max timeout_s) kısa bekle."""
        if not self._client:
            return False
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        while time.monotonic() < deadline:
            if self._connected:
                return True
            time.sleep(0.05)
        return bool(self._connected)

    def connect(
        self,
        server_addr: str,
        node_id: str,
        password: str,
    ) -> None:
        """Broker'a bağlan. username=node_id, password=password. LWT: nodes/status/{node_id} {"status": "offline"}."""
        host, port = parse_server_addr(server_addr)
        self._node_id = node_id
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            client_id=node_id,
            protocol=mqtt.MQTTv311,
            clean_session=True,
        )
        self._client.username_pw_set(username=node_id, password=password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=60)

        # LWT: connect'ten önce
        lwt_topic = TOPIC_STATUS.format(node_id)
        lwt_payload = json.dumps({"status": "offline"})
        self._client.will_set(
            lwt_topic,
            payload=lwt_payload,
            qos=1,
            retain=True,
        )
        self._connected = False
        # loop_start ile otomatik reconnect için async connect kullan.
        self._client.connect_async(host, port=port, keepalive=60)
        self._client.loop_start()

    def _on_connect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        _flags: dict,
        rc: int,
    ) -> None:
        if rc != 0:
            self._connected = False
            logger.warning("MQTT connect rc=%s", rc)
            return
        self._connected = True
        logger.info("MQTT connected")
        if self._cmd_callback and self._node_id:
            self._client.subscribe(TOPIC_CMD.format(self._node_id), qos=0)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        rc: int,
    ) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("MQTT disconnected rc=%s", rc)

    def _on_message(
        self,
        _client: mqtt.Client,
        _userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        if self._node_id and msg.topic == TOPIC_REGISTER_ACK.format(self._node_id):
            try:
                payload = msg.payload.decode("utf-8", errors="replace").strip()
            except Exception:
                payload = ""
            ok = False
            if payload.lower() == "ok":
                ok = True
            elif payload:
                try:
                    data = json.loads(payload)
                    if isinstance(data, dict) and str(data.get("status", "")).lower() == "ok":
                        ok = True
                except Exception:
                    ok = False
            self._register_ack_ok = ok
            self._register_ack_event.set()
            return
        if self._cmd_callback and msg.topic == TOPIC_CMD.format(self._node_id or ""):
            try:
                payload = msg.payload.decode("utf-8", errors="replace")
                self._cmd_callback(payload)
            except Exception as e:
                logger.exception("cmd callback error: %s", e)

    def subscribe_commands(self, callback: Callable[[str], None]) -> None:
        """nodes/cmd/{node_id} gelen mesajları callback'e verir. Connect öncesi veya sonrası çağrılabilir."""
        self._cmd_callback = callback
        if self._client and self._node_id and self._wait_connected(10.0):
            self._client.subscribe(TOPIC_CMD.format(self._node_id), qos=0)

    def subscribe_register_ack(self, node_id: str) -> None:
        """Registration handshake ack: nodes/register/ack/{node_id} → 'ok' veya {"status":"ok"}.
        Broker ACL must allow this client (username=node_id) to subscribe to nodes/register/ack/<node_id>."""
        self._node_id = node_id
        self._register_ack_ok = None
        self._register_ack_event.clear()
        if self._client and self._wait_connected(10.0):
            self._client.subscribe(TOPIC_REGISTER_ACK.format(node_id), qos=0)

    def wait_for_register_ack(self, timeout_s: float = 10.0) -> bool:
        """Ack gelene kadar bekle. Timeout sonrası False."""
        if not self._client:
            return False
        self._register_ack_event.wait(timeout=timeout_s)
        return self._register_ack_ok is True

    def publish_register(self, node_id: str, token: str, hw_serial: str) -> None:
        """nodes/register tek seferlik: {"node_id", "token", "hw_serial"}."""
        if not self._client or not self._wait_connected(10.0):
            return
        payload = json.dumps({
            "node_id": node_id,
            "token": token,
            "hw_serial": hw_serial,
        })
        self._client.publish(TOPIC_REGISTER, payload, qos=1)

    def publish_telemetry(self, node_id: str, payload_dict: Dict[str, Any]) -> None:
        """nodes/telemetry/{node_id} — contract: log_line, timestamp (zorunlu). Only publishes when connected."""
        if not self._client or not self._connected:
            return
        payload = json.dumps(payload_dict)
        self._client.publish(TOPIC_TELEMETRY.format(node_id), payload, qos=0)

    def publish_status(self, node_id: str, status: str) -> None:
        """nodes/status/{node_id} — {"status": "online"|"offline"}, retain=True önerilir."""
        if not self._client or not self._wait_connected(10.0):
            return
        payload = json.dumps({"status": status})
        self._client.publish(
            TOPIC_STATUS.format(node_id),
            payload,
            qos=1,
            retain=True,
        )

    def stop_loop(self) -> None:
        """Graceful: offline publish, disconnect (so loop can send them), then loop_stop."""
        if not self._client or not self._node_id:
            return
        try:
            self.publish_status(self._node_id, "offline")
            self._client.disconnect()
            self._client.loop_stop()
        except Exception:
            pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None
