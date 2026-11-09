"""Authoritative full-state reconciliation for incremental caches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.state.cache import InMemoryStateCache, StateSnapshot, VersionedStateDiff


class AuthoritativeStateReader(Protocol):
    def read(self, home_id: str, device_id: str) -> tuple[int, Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class ReconcileResult:
    changed: bool
    previous_sequence: Optional[int]
    authoritative_sequence: int
    difference_fields: tuple[str, ...]


class StateReconciler:
    def __init__(self, cache: InMemoryStateCache, reader: AuthoritativeStateReader) -> None:
        self.cache = cache
        self.reader = reader

    def reconcile(self, home_id: str, device_id: str) -> ReconcileResult:
        cached = self.cache.get(home_id, device_id, allow_stale=True)
        sequence, authoritative = self.reader.read(home_id, device_id)
        previous_state = dict(cached.state) if cached is not None else {}
        fields = tuple(
            sorted(
                key
                for key in set(previous_state) | set(authoritative)
                if previous_state.get(key) != authoritative.get(key)
            )
        )
        if cached is None or sequence > cached.sequence or (sequence == cached.sequence and fields):
            if cached is not None and fields:
                self.cache.invalidate(home_id, device_id)
            self.cache.apply(
                VersionedStateDiff(
                    home_id,
                    device_id,
                    sequence,
                    dict(authoritative),
                    source="authoritative-reconcile",
                    full_snapshot=True,
                )
            )
        return ReconcileResult(bool(fields), cached.sequence if cached else None, sequence, fields)


class ReadThroughStateService:
    """Uses fresh cache data, otherwise reads and repairs from the truth source."""

    def __init__(
        self,
        cache: InMemoryStateCache,
        reader: AuthoritativeStateReader,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.cache = cache
        self.reader = reader
        self.telemetry = telemetry or NoopTelemetry()

    def read(
        self,
        home_id: str,
        device_id: str,
        *,
        allow_stale_on_error: bool = False,
    ) -> StateSnapshot:
        fresh = self.cache.get(home_id, device_id)
        if fresh is not None:
            self.telemetry.increment("state.cache", attributes={"result": "hit"})
            return fresh
        stale = self.cache.get(home_id, device_id, allow_stale=True)
        self.telemetry.increment(
            "state.cache",
            attributes={"result": "stale" if stale is not None else "miss"},
        )
        try:
            sequence, state = self.reader.read(home_id, device_id)
        except Exception:
            if allow_stale_on_error and stale is not None:
                self.telemetry.increment("state.stale_fallback")
                return stale
            raise
        self.cache.apply(
            VersionedStateDiff(
                home_id,
                device_id,
                sequence,
                dict(state),
                source="authoritative-read-through",
                full_snapshot=True,
            )
        )
        restored = self.cache.get(home_id, device_id)
        if restored is None:
            raise RuntimeError("authoritative state could not be materialized in cache")
        return restored
