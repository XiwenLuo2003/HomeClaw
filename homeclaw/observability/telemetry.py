"""Small tracing facade used by runtime components and deterministic tests."""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Iterator, Mapping, MutableMapping, Protocol

from homeclaw.domain import CorrelationIds


_SENSITIVE_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
)


def redact_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow redacted copy suitable for telemetry attributes."""

    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        lowered = key.lower()
        safe[key] = "[REDACTED]" if any(part in lowered for part in _SENSITIVE_FRAGMENTS) else value
    return safe


class SpanStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


@dataclass
class SpanRecord:
    name: str
    ids: CorrelationIds
    attributes: MutableMapping[str, Any] = field(default_factory=dict)
    status: SpanStatus = SpanStatus.OK
    duration_ms: float = 0.0
    error_type: str = ""
    error_message: str = ""


class Telemetry(Protocol):
    @contextmanager
    def span(
        self,
        name: str,
        ids: CorrelationIds,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        ...

    def increment(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        ...

    def observe(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        ...


class NoopTelemetry:
    @contextmanager
    def span(
        self,
        name: str,
        ids: CorrelationIds,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        yield SpanRecord(name=name, ids=ids, attributes=redact_attributes(attributes or {}))

    def increment(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        return None

    def observe(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        return None


class InMemoryTelemetry:
    """Thread-safe telemetry sink for tests and local diagnostics."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []
        self.counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
        self.observations: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}
        self._lock = Lock()

    @staticmethod
    def _metric_key(name: str, attributes: Mapping[str, Any] | None) -> tuple[str, tuple[tuple[str, str], ...]]:
        safe = redact_attributes(attributes or {})
        labels = tuple(sorted((key, str(value)) for key, value in safe.items()))
        return name, labels

    @contextmanager
    def span(
        self,
        name: str,
        ids: CorrelationIds,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        record = SpanRecord(name=name, ids=ids, attributes=redact_attributes(attributes or {}))
        started = time.perf_counter()
        try:
            yield record
        except Exception as exc:
            record.status = SpanStatus.ERROR
            record.error_type = type(exc).__name__
            record.error_message = str(exc)
            raise
        finally:
            record.duration_ms = (time.perf_counter() - started) * 1000.0
            with self._lock:
                self.spans.append(record)

    def increment(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        key = self._metric_key(name, attributes)
        with self._lock:
            self.counters[key] = self.counters.get(key, 0) + value

    def observe(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        key = self._metric_key(name, attributes)
        with self._lock:
            self.observations.setdefault(key, []).append(value)
