"""Device state cache and incremental-diff contracts."""

from homeclaw.state.cache import (
    ApplyResult,
    InMemoryStateCache,
    StateSnapshot,
    VersionedStateDiff,
    matches_expected_state,
)
from homeclaw.state.reconcile import ReadThroughStateService, ReconcileResult, StateReconciler
from homeclaw.state.redis_adapter import RedisIdempotencyStore, RedisLease, RedisStateCache

__all__ = [
    "ApplyResult",
    "InMemoryStateCache",
    "StateSnapshot",
    "VersionedStateDiff",
    "matches_expected_state",
    "ReconcileResult",
    "ReadThroughStateService",
    "RedisIdempotencyStore",
    "RedisLease",
    "RedisStateCache",
    "StateReconciler",
]
