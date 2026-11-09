"""Optional MongoDB repositories for temporal preferences and summaries.

Collections and the Mongo client are injected so importing HomeClaw never
requires pymongo.  Writes run in a Mongo transaction when a client is supplied.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict
from datetime import datetime
from typing import Any, Optional

from homeclaw.memory.preferences import (
    PreferenceFact,
    PreferenceQuery,
    PreferenceScope,
    PreferenceSource,
    PreferenceWriteResult,
    _SCOPE_PRIORITY,
    _SOURCE_PRIORITY,
)
from homeclaw.memory.summaries import MemorySummary, SummaryPeriod


def _fact_to_document(fact: PreferenceFact) -> dict[str, Any]:
    return {
        "_id": fact.fact_id,
        "user_id": fact.user_id,
        "key": fact.key,
        "value": fact.value,
        "source": fact.source.value,
        "scope": fact.scope.value,
        "scope_id": fact.scope_id,
        "confidence": fact.confidence,
        "valid_at": fact.valid_at,
        "invalid_at": fact.invalid_at,
        "expires_at": fact.expires_at,
        "supersedes": list(fact.supersedes),
    }


def _document_to_fact(document: dict[str, Any]) -> PreferenceFact:
    return PreferenceFact(
        user_id=document["user_id"],
        key=document["key"],
        value=document["value"],
        source=PreferenceSource(document["source"]),
        scope=PreferenceScope(document["scope"]),
        scope_id=document.get("scope_id"),
        confidence=float(document.get("confidence", 1.0)),
        valid_at=document["valid_at"],
        invalid_at=document.get("invalid_at"),
        expires_at=document.get("expires_at"),
        fact_id=str(document["_id"]),
        supersedes=tuple(document.get("supersedes", ())),
    )


class MongoPreferenceStore:
    def __init__(
        self,
        collection: Any,
        client: Any | None = None,
        maximum_attempts: int = 3,
    ) -> None:
        self.collection = collection
        self.client = client
        self.maximum_attempts = maximum_attempts

    def add(self, fact: PreferenceFact) -> PreferenceWriteResult:
        for attempt in range(1, self.maximum_attempts + 1):
            try:
                return self._add_once(fact)
            except Exception as exc:
                retryable = (
                    getattr(exc, "code", None) == 11000
                    or (
                        callable(getattr(exc, "has_error_label", None))
                        and (
                            exc.has_error_label("TransientTransactionError")
                            or exc.has_error_label("UnknownTransactionCommitResult")
                        )
                    )
                )
                if not retryable or attempt >= self.maximum_attempts:
                    raise
        raise AssertionError("unreachable")

    def _add_once(self, fact: PreferenceFact) -> PreferenceWriteResult:
        session_context = self.client.start_session() if self.client is not None else nullcontext(None)
        with session_context as session:
            transaction = session.start_transaction() if session is not None else nullcontext()
            with transaction:
                existing = self.collection.find_one({"_id": fact.fact_id}, session=session)
                if existing:
                    restored = _document_to_fact(existing)
                    return PreferenceWriteResult(
                        restored, restored.invalid_at is None, reason="duplicate"
                    )
                query = {
                    "user_id": fact.user_id,
                    "key": fact.key,
                    "scope": fact.scope.value,
                    "scope_id": fact.scope_id,
                    "invalid_at": None,
                    "valid_at": {"$lte": fact.valid_at},
                    "$or": [{"expires_at": None}, {"expires_at": {"$gt": fact.valid_at}}],
                }
                conflicts = [_document_to_fact(item) for item in self.collection.find(query, session=session)]
                strongest = max(
                    conflicts,
                    key=lambda item: (
                        _SOURCE_PRIORITY[item.source], item.valid_at, item.confidence
                    ),
                    default=None,
                )
                if strongest is not None and _SOURCE_PRIORITY[strongest.source] > _SOURCE_PRIORITY[fact.source]:
                    inactive = PreferenceFact(
                        **{
                            **fact.__dict__,
                            "invalid_at": fact.valid_at,
                        }
                    )
                    self.collection.insert_one(_fact_to_document(inactive), session=session)
                    return PreferenceWriteResult(
                        inactive,
                        False,
                        reason=f"lower-priority {fact.source.value} fact cannot override {strongest.source.value}",
                    )
                invalidated = tuple(item.fact_id for item in conflicts)
                if invalidated:
                    self.collection.update_many(
                        {"_id": {"$in": list(invalidated)}, "invalid_at": None},
                        {"$set": {"invalid_at": fact.valid_at}},
                        session=session,
                    )
                active = PreferenceFact(**{**fact.__dict__, "supersedes": invalidated})
                self.collection.insert_one(_fact_to_document(active), session=session)
                return PreferenceWriteResult(active, True, invalidated)

    def resolve(self, query: PreferenceQuery) -> Optional[PreferenceFact]:
        scope_conditions: list[dict[str, Any]] = [{"scope": PreferenceScope.GLOBAL.value}]
        if query.device_id:
            scope_conditions.append(
                {"scope": PreferenceScope.DEVICE.value, "scope_id": query.device_id}
            )
        if query.room_id:
            scope_conditions.append({"scope": PreferenceScope.ROOM.value, "scope_id": query.room_id})
        if query.context_id:
            scope_conditions.append(
                {"scope": PreferenceScope.CONTEXT.value, "scope_id": query.context_id}
            )
        documents = self.collection.find(
            {
                "user_id": query.user_id,
                "key": query.key,
                "valid_at": {"$lte": query.at},
                "$and": [
                    {"$or": [{"invalid_at": None}, {"invalid_at": {"$gt": query.at}}]},
                    {"$or": [{"expires_at": None}, {"expires_at": {"$gt": query.at}}]},
                    {"$or": scope_conditions},
                ],
            }
        )
        facts = [_document_to_fact(item) for item in documents]
        return max(
            facts,
            key=lambda fact: (
                _SCOPE_PRIORITY[fact.scope],
                _SOURCE_PRIORITY[fact.source],
                fact.valid_at,
                fact.confidence,
            ),
            default=None,
        )

    def history(self, user_id: str, key: str) -> tuple[PreferenceFact, ...]:
        documents = self.collection.find({"user_id": user_id, "key": key}).sort("valid_at", 1)
        return tuple(_document_to_fact(item) for item in documents)

    def revoke(self, user_id: str, fact_id: str, at: datetime) -> PreferenceFact:
        existing = self.collection.find_one({"_id": fact_id, "user_id": user_id})
        if existing is None:
            raise KeyError(fact_id)
        fact = _document_to_fact(existing)
        if at < fact.valid_at:
            raise ValueError("preference revocation cannot precede valid_at")
        if fact.invalid_at is not None:
            return fact
        result = self.collection.update_one(
            {"_id": fact_id, "user_id": user_id, "invalid_at": None},
            {"$set": {"invalid_at": at}},
        )
        if getattr(result, "matched_count", 0) == 0:
            current = self.collection.find_one({"_id": fact_id, "user_id": user_id})
            if current is None:
                raise KeyError(fact_id)
            return _document_to_fact(current)
        return PreferenceFact(**{**fact.__dict__, "invalid_at": at})


def _summary_from_document(document: dict[str, Any]) -> MemorySummary:
    return MemorySummary(
        user_id=document["user_id"],
        period=SummaryPeriod(document["period"]),
        period_key=document["period_key"],
        text=document["text"],
        source_event_ids=tuple(document.get("source_event_ids", ())),
        version=int(document.get("version", 1)),
        summary_id=str(document["_id"]),
        created_at=document["created_at"],
    )


class MongoSummaryStore:
    """Optimistic, idempotent daily/monthly summary materialization."""

    def __init__(self, collection: Any, maximum_attempts: int = 3) -> None:
        self.collection = collection
        self.maximum_attempts = maximum_attempts

    def get(
        self, user_id: str, period: SummaryPeriod, period_key: str
    ) -> Optional[MemorySummary]:
        document = self.collection.find_one(
            {"user_id": user_id, "period": period.value, "period_key": period_key}
        )
        return _summary_from_document(document) if document else None

    def put_if_changed(self, summary: MemorySummary) -> MemorySummary:
        query = {
            "user_id": summary.user_id,
            "period": summary.period.value,
            "period_key": summary.period_key,
        }
        for _ in range(self.maximum_attempts):
            current_raw = self.collection.find_one(query)
            if current_raw is None:
                document = {
                    "_id": summary.summary_id,
                    **query,
                    "text": summary.text,
                    "source_event_ids": list(summary.source_event_ids),
                    "version": 1,
                    "created_at": summary.created_at,
                }
                try:
                    self.collection.insert_one(document)
                    return _summary_from_document(document)
                except Exception:
                    # A concurrent insert may have won the unique compound index.
                    if self.collection.find_one(query) is None:
                        raise
                    continue
            current = _summary_from_document(current_raw)
            if current.source_event_ids == summary.source_event_ids:
                return current
            result = self.collection.update_one(
                {"_id": current.summary_id, "version": current.version},
                {
                    "$set": {
                        "text": summary.text,
                        "source_event_ids": list(summary.source_event_ids),
                        "created_at": summary.created_at,
                    },
                    "$inc": {"version": 1},
                },
            )
            if getattr(result, "matched_count", 0) == 1:
                stored = self.collection.find_one({"_id": current.summary_id})
                return _summary_from_document(stored)
        raise RuntimeError("concurrent Mongo summary update did not converge")
