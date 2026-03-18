"""
MQTT client: connect, subscribe to bind/telemetry/status, route to state; publish commands.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import paho.mqtt.client as mqtt

if TYPE_CHECKING:
    from .state import State

logger = logging.getLogger(__name__)

TOPIC_BIND = "nodes/bind"
TOPIC_TELEMETRY = "nodes/telemetry/+"
TOPIC_STATUS = "nodes/status/+"


def _node_id_from_topic(prefix: str, topic: str) -> str | None:
    """e.g. prefix 'nodes/telemetry/' -> topic 'nodes/telemetry/abc' -> 'abc'."""
    if not topic.startswith(prefix) or topic == prefix:
        return None
    rest = topic[len(prefix) :].strip("/")
    if "/" in rest:
        return None
    return rest if rest else None


class MQTTHandler:
    def __init__(
        self,
        state: State,
        broker: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        self._state = state
        self._broker = broker
        self._port = port
        self._username = username
        self._password = password
        self._client: mqtt.Client | None = None

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: object,
        flags: dict,
        reason_code: int,
        properties: object | None = None,
    ) -> None:
        if reason_code != 0:
            logger.warning("MQTT connect reason_code=%s", reason_code)
            return
        client.subscribe(TOPIC_BIND, qos=1)
        client.subscribe(TOPIC_TELEMETRY, qos=0)
        client.subscribe(TOPIC_STATUS, qos=0)
        logger.info("MQTT connected and subscribed")

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: object,
        msg: mqtt.MQTTMessage,
    ) -> None:
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
        except UnicodeDecodeError:
            logger.debug("Invalid UTF-8 on %s", topic)
            return

        if topic == TOPIC_BIND:
            try:
                data = json.loads(payload)
                node_id = data.get("node_id")
                one_time_token = data.get("one_time_token")
                hardware_serial = data.get("hardware_serial")
                if not all([node_id, one_time_token, hardware_serial]):
                    logger.warning("nodes/bind missing fields")
                    return
                if not self._state.try_bind(
                    str(node_id), str(one_time_token), str(hardware_serial)
                ):
                    logger.warning("Bind rejected for node_id=%s", node_id)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON on nodes/bind")
            return

        if topic.startswith("nodes/telemetry/"):
            node_id = _node_id_from_topic("nodes/telemetry/", topic)
            if not node_id or not self._state.has_node(node_id):
                return
            try:
                data = json.loads(payload)
                log_line = data.get("log_line")
                timestamp = data.get("timestamp", "")
                if log_line is not None:
                    self._state.append_telemetry(
                        node_id, str(log_line), str(timestamp)
                    )
            except json.JSONDecodeError:
                logger.debug("Invalid JSON telemetry from %s", node_id)
            return

        if topic.startswith("nodes/status/"):
            node_id = _node_id_from_topic("nodes/status/", topic)
            if not node_id or not self._state.has_node(node_id):
                return
            try:
                data = json.loads(payload)
                status = data.get("status")
                if status in ("online", "offline"):
                    self._state.set_status(node_id, status)
                else:
                    self._state.set_status(node_id, "unknown")
            except json.JSONDecodeError:
                self._state.set_status(node_id, "unknown")
            return

    def start(self) -> None:
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv311,
        )
        self._client.username_pw_set(self._username, self._password)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        try:
            self._client.connect(self._broker, self._port, 60)
        except Exception as e:
            logger.error("MQTT connect failed: %s", e)
            raise
        self._client.loop_start()

    def stop(self) -> None:
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None

    def publish_cmd(self, node_id: str, text: str) -> None:
        if not self._client or not self._client.is_connected():
            logger.warning("MQTT not connected, cannot publish command")
            return
        if not self._state.has_node(node_id):
            logger.warning("Refusing to publish command to unbound node_id=%s", node_id)
            return
        topic = f"nodes/cmd/{node_id}"
        self._client.publish(topic, text, qos=0)
