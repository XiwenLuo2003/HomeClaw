"""Optional Paho MQTT v2 transport adapter."""

from __future__ import annotations

import json
import time
from threading import Condition, RLock
from typing import Callable, Mapping, Optional

from homeclaw.mqtt.transport import MqttMessage, PublishReceipt


class PahoMqttTransport:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        *,
        client_id: str = "homeclaw-mqtt-bridge",
        username: Optional[str] = None,
        password: Optional[str] = None,
        tls: bool = False,
        keepalive: int = 60,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError("paho-mqtt is required only for a real MQTT deployment") from exc
        self._mqtt = mqtt
        self._messages: list[MqttMessage] = []
        self._condition = Condition(RLock())
        self._subscriptions: set[str] = set()
        self._subscription_acks: set[int] = set()
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self._client.on_message = self._on_message
        self._client.on_subscribe = self._on_subscribe
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        if username is not None:
            self._client.username_pw_set(username, password)
        if tls:
            self._client.tls_set()
        self._client.connect(host, port, keepalive)
        self._client.loop_start()

    def _on_message(self, client, userdata, message) -> None:
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, Mapping):
                payload = {"value": payload}
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {"raw": message.payload.hex()}
        with self._condition:
            self._messages.append(MqttMessage(message.topic, payload, retained=message.retain))
            self._condition.notify_all()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        with self._condition:
            self._subscription_acks.add(int(mid))
            self._condition.notify_all()

    def publish(self, topic: str, payload: Mapping[str, object], qos: int = 1) -> PublishReceipt:
        info = self._client.publish(
            topic,
            json.dumps(dict(payload), separators=(",", ":"), ensure_ascii=False),
            qos=qos,
            retain=False,
        )
        try:
            info.wait_for_publish(timeout=5.0)
        except RuntimeError as exc:
            return PublishReceipt(False, message_id=info.mid, reason=str(exc))
        accepted = info.rc == self._mqtt.MQTT_ERR_SUCCESS and info.is_published()
        reason = "" if accepted else f"publish not confirmed, rc={info.rc}"
        return PublishReceipt(accepted, message_id=info.mid, reason=reason)

    def ensure_subscription(self, topic: str, qos: int = 1) -> None:
        if topic in self._subscriptions:
            return
        result, message_id = self._client.subscribe(topic, qos=qos)
        if result != self._mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT subscribe failed with rc={result}")
        deadline = time.monotonic() + 5.0
        with self._condition:
            while message_id not in self._subscription_acks:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"MQTT SUBACK timed out for topic {topic}")
                self._condition.wait(remaining)
            self._subscription_acks.remove(message_id)
        self._subscriptions.add(topic)

    def wait_for_message(
        self,
        topic: str,
        predicate: Callable[[MqttMessage], bool],
        timeout_seconds: float,
    ) -> Optional[MqttMessage]:
        self.ensure_subscription(topic, qos=1)
        deadline = time.monotonic() + timeout_seconds
        with self._condition:
            while True:
                for index, message in enumerate(self._messages):
                    if message.topic == topic and predicate(message):
                        return self._messages.pop(index)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
