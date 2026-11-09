"""MQTT transport boundary with an in-memory deterministic implementation."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from threading import Condition, RLock
from typing import Callable, Mapping, Optional, Protocol

from homeclaw.domain.models import utc_now


@dataclass(frozen=True)
class PublishReceipt:
    accepted: bool
    message_id: Optional[int] = None
    reason: str = ""


@dataclass(frozen=True)
class MqttMessage:
    topic: str
    payload: Mapping[str, object]
    retained: bool = False
    received_at: datetime = field(default_factory=utc_now)


class MqttTransport(Protocol):
    def ensure_subscription(self, topic: str, qos: int = 1) -> None:
        ...

    def publish(self, topic: str, payload: Mapping[str, object], qos: int = 1) -> PublishReceipt:
        ...

    def wait_for_message(
        self,
        topic: str,
        predicate: Callable[[MqttMessage], bool],
        timeout_seconds: float,
    ) -> Optional[MqttMessage]:
        ...


class InMemoryMqttTransport:
    """A broker-like transport used by bridge integration tests."""

    def __init__(self) -> None:
        self.published: list[MqttMessage] = []
        self._messages: list[MqttMessage] = []
        self._condition = Condition(RLock())
        self.on_publish: Optional[
            Callable[[str, Mapping[str, object], "InMemoryMqttTransport"], None]
        ] = None
        self.accept_publish = True

    def ensure_subscription(self, topic: str, qos: int = 1) -> None:
        if qos not in (0, 1, 2):
            raise ValueError("MQTT QoS must be 0, 1, or 2")

    def publish(self, topic: str, payload: Mapping[str, object], qos: int = 1) -> PublishReceipt:
        if qos not in (0, 1, 2):
            raise ValueError("MQTT QoS must be 0, 1, or 2")
        message = MqttMessage(topic=topic, payload=dict(payload))
        with self._condition:
            self.published.append(message)
        if not self.accept_publish:
            return PublishReceipt(False, reason="broker rejected publish")
        if self.on_publish is not None:
            self.on_publish(topic, payload, self)
        return PublishReceipt(True, message_id=len(self.published))

    def inject(self, topic: str, payload: Mapping[str, object], *, retained: bool = False) -> None:
        with self._condition:
            self._messages.append(MqttMessage(topic, dict(payload), retained=retained))
            self._condition.notify_all()

    def wait_for_message(
        self,
        topic: str,
        predicate: Callable[[MqttMessage], bool],
        timeout_seconds: float,
    ) -> Optional[MqttMessage]:
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
