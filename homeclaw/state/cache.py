"""Version-aware state cache with stale-state semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import RLock
from typing import Any, Mapping, Optional

from homeclaw.domain.models import utc_now


class ApplyResult(str, Enum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"
    GAP = "gap"


@dataclass(frozen=True)
class VersionedStateDiff:
    home_id: str
    device_id: str
    sequence: int
    changes: Mapping[str, Any]
    observed_at: datetime = field(default_factory=utc_now)
    source: str = "mqtt"
    full_snapshot: bool = False

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("state sequence must be non-negative")
        if not self.changes:
            raise ValueError("state diff must contain changes")


@dataclass(frozen=True)
class StateSnapshot:
    home_id: str
    device_id: str
    sequence: int
    state: Mapping[str, Any]
    observed_at: datetime
    expires_at: datetime
    source: str

    @property
    def stale(self) -> bool:
        return utc_now() >= self.expires_at


def _merge_nested(base: dict[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge_nested(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def matches_expected_state(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Recursively require every expected field while allowing extra observed fields."""

    for key, expected_value in expected.items():
        if key not in observed:
            return False
        observed_value = observed[key]
        if isinstance(expected_value, Mapping):
            if not isinstance(observed_value, Mapping):
                return False
            if not matches_expected_state(observed_value, expected_value):
                return False
        elif observed_value != expected_value:
            return False
    return True


class InMemoryStateCache:
    def __init__(self, ttl_seconds: float = 60.0) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._items: dict[tuple[str, str], StateSnapshot] = {}
        self._lock = RLock()

    def apply(self, diff: VersionedStateDiff) -> ApplyResult:
        key = (diff.home_id, diff.device_id)
        with self._lock:
            current = self._items.get(key)
            if current is not None:
                if diff.sequence < current.sequence:
                    return ApplyResult.OUT_OF_ORDER
                if diff.sequence == current.sequence:
                    return ApplyResult.DUPLICATE
                if diff.sequence > current.sequence + 1 and not diff.full_snapshot:
                    return ApplyResult.GAP
                state = (
                    dict(diff.changes)
                    if diff.full_snapshot
                    else _merge_nested(dict(current.state), diff.changes)
                )
            else:
                state = dict(diff.changes)
            self._items[key] = StateSnapshot(
                home_id=diff.home_id,
                device_id=diff.device_id,
                sequence=diff.sequence,
                state=state,
                observed_at=diff.observed_at,
                expires_at=diff.observed_at + timedelta(seconds=self.ttl_seconds),
                source=diff.source,
            )
            return ApplyResult.APPLIED

    def get(self, home_id: str, device_id: str, *, allow_stale: bool = False) -> Optional[StateSnapshot]:
        with self._lock:
            item = self._items.get((home_id, device_id))
        if item is None or (item.stale and not allow_stale):
            return None
        return item

    def invalidate(self, home_id: str, device_id: str) -> None:
        with self._lock:
            self._items.pop((home_id, device_id), None)
