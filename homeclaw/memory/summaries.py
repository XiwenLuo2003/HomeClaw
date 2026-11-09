"""Idempotent daily/monthly summary materialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from threading import RLock
from typing import Callable, Optional, Protocol, Sequence

from homeclaw.domain.models import new_id, utc_now


class SummaryPeriod(str, Enum):
    DAILY = "daily"
    MONTHLY = "monthly"


@dataclass(frozen=True)
class MemoryEvent:
    user_id: str
    content: str
    occurred_at: datetime
    event_id: str = field(default_factory=lambda: new_id("memory"))
    source: str = "interaction"


@dataclass(frozen=True)
class MemorySummary:
    user_id: str
    period: SummaryPeriod
    period_key: str
    text: str
    source_event_ids: tuple[str, ...]
    version: int = 1
    summary_id: str = field(default_factory=lambda: new_id("summary"))
    created_at: datetime = field(default_factory=utc_now)


class SummaryStore(Protocol):
    def get(self, user_id: str, period: SummaryPeriod, period_key: str) -> Optional[MemorySummary]:
        ...

    def put_if_changed(self, summary: MemorySummary) -> MemorySummary:
        ...


class InMemorySummaryStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, SummaryPeriod, str], MemorySummary] = {}
        self._lock = RLock()

    def get(self, user_id: str, period: SummaryPeriod, period_key: str) -> Optional[MemorySummary]:
        with self._lock:
            return self._items.get((user_id, period, period_key))

    def put_if_changed(self, summary: MemorySummary) -> MemorySummary:
        key = (summary.user_id, summary.period, summary.period_key)
        with self._lock:
            current = self._items.get(key)
            if current is not None and current.source_event_ids == summary.source_event_ids:
                return current
            version = current.version + 1 if current is not None else 1
            stored = MemorySummary(
                user_id=summary.user_id,
                period=summary.period,
                period_key=summary.period_key,
                text=summary.text,
                source_event_ids=summary.source_event_ids,
                version=version,
            )
            self._items[key] = stored
            return stored


class SummaryService:
    def __init__(
        self,
        store: SummaryStore,
        summarizer: Callable[[Sequence[MemoryEvent]], str],
    ) -> None:
        self.store = store
        self.summarizer = summarizer

    def materialize(
        self,
        user_id: str,
        period: SummaryPeriod,
        period_key: str,
        events: Sequence[MemoryEvent],
    ) -> MemorySummary:
        selected = tuple(
            sorted(
                (event for event in events if event.user_id == user_id),
                key=lambda event: (event.occurred_at, event.event_id),
            )
        )
        if not selected:
            raise ValueError("cannot summarize an empty event set")
        text = self.summarizer(selected)
        if not text.strip():
            raise ValueError("summarizer returned empty text")
        return self.store.put_if_changed(
            MemorySummary(
                user_id=user_id,
                period=period,
                period_key=period_key,
                text=text,
                source_event_ids=tuple(event.event_id for event in selected),
            )
        )
