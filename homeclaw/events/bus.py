"""Synchronous in-process event bus for modular-monolith execution."""

from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Callable

from homeclaw.domain import MessageEnvelope


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable[[MessageEnvelope], None]]] = defaultdict(list)
        self._seen: set[str] = set()
        self._lock = RLock()

    def subscribe(self, message_type: str, handler: Callable[[MessageEnvelope], None]) -> None:
        with self._lock:
            self._handlers[message_type].append(handler)

    def publish(self, message: MessageEnvelope) -> bool:
        with self._lock:
            if message.message_id in self._seen:
                return False
            self._seen.add(message.message_id)
            handlers = list(self._handlers.get(message.message_type, ()))
        for handler in handlers:
            handler(message)
        return True
