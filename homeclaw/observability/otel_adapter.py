"""Optional OpenTelemetry adapter loaded only in configured deployments."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from homeclaw.domain import CorrelationIds
from homeclaw.observability.telemetry import SpanRecord, SpanStatus, redact_attributes


class OpenTelemetryAdapter:
    def __init__(self, service_name: str = "homeclaw") -> None:
        try:
            from opentelemetry import metrics, trace
        except ImportError as exc:
            raise RuntimeError(
                "OpenTelemetry SDK is optional; install deployment extras before enabling this adapter"
            ) from exc
        self._trace = trace
        self._tracer = trace.get_tracer(service_name)
        self._meter = metrics.get_meter(service_name)
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}

    @contextmanager
    def span(
        self,
        name: str,
        ids: CorrelationIds,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[SpanRecord]:
        safe = redact_attributes(attributes or {})
        safe.update(
            {
                "homeclaw.trace_id": ids.trace_id,
                "homeclaw.request_id": ids.request_id,
                "homeclaw.task_id": ids.task_id,
            }
        )
        if ids.command_id:
            safe["homeclaw.command_id"] = ids.command_id
        record = SpanRecord(name=name, ids=ids, attributes=safe)
        started = time.perf_counter()
        with self._tracer.start_as_current_span(name, attributes=safe) as otel_span:
            try:
                yield record
            except Exception as exc:
                record.status = SpanStatus.ERROR
                record.error_type = type(exc).__name__
                record.error_message = str(exc)
                otel_span.record_exception(exc)
                otel_span.set_status(self._trace.Status(self._trace.StatusCode.ERROR, str(exc)))
                raise
            finally:
                record.duration_ms = (time.perf_counter() - started) * 1000.0

    def increment(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        counter = self._counters.setdefault(name, self._meter.create_counter(name))
        counter.add(value, redact_attributes(attributes or {}))

    def observe(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        histogram = self._histograms.setdefault(name, self._meter.create_histogram(name))
        histogram.record(value, redact_attributes(attributes or {}))
