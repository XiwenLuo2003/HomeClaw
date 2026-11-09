"""Vendor-neutral observability interfaces.

Production adapters may export these records through OpenTelemetry.  Tests use
the in-memory implementation, keeping the core runtime free of mandatory SDKs.
"""

from homeclaw.observability.telemetry import (
    InMemoryTelemetry,
    NoopTelemetry,
    SpanRecord,
    SpanStatus,
    Telemetry,
    redact_attributes,
)
from homeclaw.observability.otel_adapter import OpenTelemetryAdapter

__all__ = [
    "InMemoryTelemetry",
    "NoopTelemetry",
    "OpenTelemetryAdapter",
    "SpanRecord",
    "SpanStatus",
    "Telemetry",
    "redact_attributes",
]
