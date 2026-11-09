"""Append-only temporal preferences with deterministic conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from threading import RLock
from typing import Any, Optional, Protocol

from homeclaw.domain.models import new_id, utc_now


class PreferenceSource(str, Enum):
    INFERRED = "inferred"
    SYSTEM = "system"
    EXPLICIT = "explicit"


class PreferenceScope(str, Enum):
    GLOBAL = "global"
    CONTEXT = "context"
    ROOM = "room"
    DEVICE = "device"


_SOURCE_PRIORITY = {
    PreferenceSource.INFERRED: 1,
    PreferenceSource.SYSTEM: 2,
    PreferenceSource.EXPLICIT: 3,
}

_SCOPE_PRIORITY = {
    PreferenceScope.GLOBAL: 0,
    PreferenceScope.CONTEXT: 1,
    PreferenceScope.ROOM: 2,
    PreferenceScope.DEVICE: 3,
}


@dataclass(frozen=True)
class PreferenceFact:
    user_id: str
    key: str
    value: Any
    source: PreferenceSource
    scope: PreferenceScope = PreferenceScope.GLOBAL
    scope_id: Optional[str] = None
    confidence: float = 1.0
    valid_at: datetime = field(default_factory=utc_now)
    invalid_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    fact_id: str = field(default_factory=lambda: new_id("pref"))
    supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.user_id.strip() or not self.key.strip():
            raise ValueError("preference user_id and key are required")
        if self.scope is PreferenceScope.GLOBAL and self.scope_id is not None:
            raise ValueError("global preference must not set scope_id")
        if self.scope is not PreferenceScope.GLOBAL and not self.scope_id:
            raise ValueError("non-global preference requires scope_id")
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError("preference confidence must be in [0, 1]")
        if self.invalid_at is not None and self.invalid_at < self.valid_at:
            raise ValueError("invalid_at cannot precede valid_at")
        if self.expires_at is not None and self.expires_at <= self.valid_at:
            raise ValueError("expires_at must follow valid_at")

    def active_at(self, moment: datetime) -> bool:
        return (
            self.valid_at <= moment
            and (self.invalid_at is None or moment < self.invalid_at)
            and (self.expires_at is None or moment < self.expires_at)
        )


@dataclass(frozen=True)
class PreferenceQuery:
    user_id: str
    key: str
    device_id: Optional[str] = None
    room_id: Optional[str] = None
    context_id: Optional[str] = None
    at: datetime = field(default_factory=utc_now)


@dataclass(frozen=True)
class PreferenceWriteResult:
    fact: PreferenceFact
    active: bool
    invalidated_fact_ids: tuple[str, ...] = ()
    reason: str = ""


class PreferenceStore(Protocol):
    def add(self, fact: PreferenceFact) -> PreferenceWriteResult:
        ...

    def resolve(self, query: PreferenceQuery) -> Optional[PreferenceFact]:
        ...

    def history(self, user_id: str, key: str) -> tuple[PreferenceFact, ...]:
        ...

    def revoke(self, user_id: str, fact_id: str, at: datetime) -> PreferenceFact:
        ...


class InMemoryPreferenceStore:
    """Reference implementation mirroring the intended Mongo append-only model."""

    def __init__(self) -> None:
        self._facts: dict[str, PreferenceFact] = {}
        self._lock = RLock()

    def add(self, fact: PreferenceFact) -> PreferenceWriteResult:
        with self._lock:
            if fact.fact_id in self._facts:
                existing = self._facts[fact.fact_id]
                return PreferenceWriteResult(existing, existing.invalid_at is None, reason="duplicate")

            conflicts = [
                existing
                for existing in self._facts.values()
                if existing.user_id == fact.user_id
                and existing.key == fact.key
                and existing.scope is fact.scope
                and existing.scope_id == fact.scope_id
                and existing.active_at(fact.valid_at)
            ]
            strongest = max(
                conflicts,
                key=lambda item: (_SOURCE_PRIORITY[item.source], item.valid_at, item.confidence),
                default=None,
            )
            if strongest is not None and _SOURCE_PRIORITY[strongest.source] > _SOURCE_PRIORITY[fact.source]:
                inactive = replace(fact, invalid_at=fact.valid_at)
                self._facts[inactive.fact_id] = inactive
                return PreferenceWriteResult(
                    inactive,
                    False,
                    reason=f"lower-priority {fact.source.value} fact cannot override {strongest.source.value}",
                )

            invalidated: list[str] = []
            for existing in conflicts:
                updated = replace(existing, invalid_at=fact.valid_at)
                self._facts[existing.fact_id] = updated
                invalidated.append(existing.fact_id)
            active = replace(fact, supersedes=tuple(invalidated))
            self._facts[active.fact_id] = active
            return PreferenceWriteResult(active, True, tuple(invalidated))

    def resolve(self, query: PreferenceQuery) -> Optional[PreferenceFact]:
        with self._lock:
            candidates = [
                fact
                for fact in self._facts.values()
                if fact.user_id == query.user_id
                and fact.key == query.key
                and fact.active_at(query.at)
                and self._scope_matches(fact, query)
            ]
        return max(
            candidates,
            key=lambda fact: (
                _SCOPE_PRIORITY[fact.scope],
                _SOURCE_PRIORITY[fact.source],
                fact.valid_at,
                fact.confidence,
            ),
            default=None,
        )

    def history(self, user_id: str, key: str) -> tuple[PreferenceFact, ...]:
        with self._lock:
            facts = [
                fact for fact in self._facts.values() if fact.user_id == user_id and fact.key == key
            ]
        return tuple(sorted(facts, key=lambda fact: (fact.valid_at, fact.fact_id)))

    def revoke(self, user_id: str, fact_id: str, at: datetime) -> PreferenceFact:
        with self._lock:
            fact = self._facts.get(fact_id)
            if fact is None or fact.user_id != user_id:
                raise KeyError(fact_id)
            if at < fact.valid_at:
                raise ValueError("preference revocation cannot precede valid_at")
            if fact.invalid_at is not None:
                return fact
            revoked = replace(fact, invalid_at=at)
            self._facts[fact_id] = revoked
            return revoked

    @staticmethod
    def _scope_matches(fact: PreferenceFact, query: PreferenceQuery) -> bool:
        return (
            fact.scope is PreferenceScope.GLOBAL
            or (fact.scope is PreferenceScope.DEVICE and fact.scope_id == query.device_id)
            or (fact.scope is PreferenceScope.ROOM and fact.scope_id == query.room_id)
            or (fact.scope is PreferenceScope.CONTEXT and fact.scope_id == query.context_id)
        )
