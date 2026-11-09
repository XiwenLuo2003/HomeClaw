"""Optional Redis cache, lease, and command-idempotency adapters.

The module accepts an injected redis-py client and therefore remains importable
without redis-py installed in the base HomeClaw environment.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Mapping, Optional

from homeclaw.domain import (
    ActionStatus,
    CorrelationIds,
    ErrorCode,
    ErrorDetail,
    ExecutionEvidence,
)
from homeclaw.domain.models import new_id, utc_now
from homeclaw.state.cache import ApplyResult, StateSnapshot, VersionedStateDiff


_APPLY_STATE_LUA = """
local current = redis.call('HGET', KEYS[1], 'sequence')
if current and tonumber(current) >= tonumber(ARGV[1]) then
  return 0
end
if current and tonumber(ARGV[1]) > tonumber(current) + 1 and ARGV[7] ~= '1' then
  return -1
end
redis.call('HSET', KEYS[1],
  'sequence', ARGV[1],
  'state_json', ARGV[2],
  'observed_at', ARGV[3],
  'expires_at', ARGV[4],
  'source', ARGV[5])
redis.call('PEXPIRE', KEYS[1], ARGV[6])
return 1
"""

_RELEASE_LEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def _decode(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _decoded_hash(raw: Mapping[Any, Any]) -> dict[str, str]:
    return {_decode(key): _decode(value) for key, value in raw.items()}


def _merge(base: dict[str, Any], changes: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in changes.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


class RedisStateCache:
    def __init__(self, client: Any, ttl_seconds: float = 60.0, prefix: str = "homeclaw:state") -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def _key(self, home_id: str, device_id: str) -> str:
        return f"{self.prefix}:{home_id}:{device_id}"

    def apply(self, diff: VersionedStateDiff) -> ApplyResult:
        key = self._key(diff.home_id, diff.device_id)
        raw = _decoded_hash(self.client.hgetall(key))
        current_sequence = int(raw.get("sequence", -1))
        if diff.sequence < current_sequence:
            return ApplyResult.OUT_OF_ORDER
        if diff.sequence == current_sequence:
            return ApplyResult.DUPLICATE
        if current_sequence >= 0 and diff.sequence > current_sequence + 1 and not diff.full_snapshot:
            return ApplyResult.GAP
        current_state = json.loads(raw.get("state_json", "{}"))
        state = dict(diff.changes) if diff.full_snapshot else _merge(current_state, diff.changes)
        expires_at = diff.observed_at + timedelta(seconds=self.ttl_seconds)
        applied = self.client.eval(
            _APPLY_STATE_LUA,
            1,
            key,
            diff.sequence,
            json.dumps(state, separators=(",", ":"), sort_keys=True),
            diff.observed_at.isoformat(),
            expires_at.isoformat(),
            diff.source,
            int(self.ttl_seconds * 1000),
            "1" if diff.full_snapshot else "0",
        )
        if applied:
            return ApplyResult.APPLIED
        if int(applied) == -1:
            return ApplyResult.GAP
        latest = _decoded_hash(self.client.hgetall(key))
        latest_sequence = int(latest.get("sequence", -1))
        return ApplyResult.DUPLICATE if latest_sequence == diff.sequence else ApplyResult.OUT_OF_ORDER

    def get(self, home_id: str, device_id: str, *, allow_stale: bool = False) -> Optional[StateSnapshot]:
        raw = _decoded_hash(self.client.hgetall(self._key(home_id, device_id)))
        if not raw:
            return None
        snapshot = StateSnapshot(
            home_id,
            device_id,
            int(raw["sequence"]),
            json.loads(raw["state_json"]),
            datetime.fromisoformat(raw["observed_at"]),
            datetime.fromisoformat(raw["expires_at"]),
            raw["source"],
        )
        return snapshot if allow_stale or not snapshot.stale else None


class RedisLease:
    def __init__(self, client: Any, name: str, ttl_ms: int = 10_000, prefix: str = "homeclaw:lock") -> None:
        self.client = client
        self.key = f"{prefix}:{name}"
        self.ttl_ms = ttl_ms
        self.token = new_id("lease")

    def acquire(self) -> bool:
        return bool(self.client.set(self.key, self.token, nx=True, px=self.ttl_ms))

    def release(self) -> bool:
        return bool(self.client.eval(_RELEASE_LEASE_LUA, 1, self.key, self.token))


class RedisIdempotencyStore:
    PENDING = "__pending__"

    def __init__(self, client: Any, ttl_seconds: int = 86_400, prefix: str = "homeclaw:command") -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def _key(self, command_id: str) -> str:
        return f"{self.prefix}:{command_id}"

    def claim(self, command_id: str) -> bool:
        return bool(self.client.set(self._key(command_id), self.PENDING, nx=True, ex=self.ttl_seconds))

    def put(self, command_id: str, evidence: ExecutionEvidence) -> None:
        self.client.set(
            self._key(command_id),
            json.dumps(evidence.to_dict(), separators=(",", ":"), sort_keys=True),
            ex=self.ttl_seconds,
        )

    def get(self, command_id: str) -> Optional[ExecutionEvidence]:
        raw = self.client.get(self._key(command_id))
        if raw is None or _decode(raw) == self.PENDING:
            return None
        item = json.loads(_decode(raw))
        ids = item["ids"]
        error_raw = item.get("error")
        error = None
        if error_raw:
            error = ErrorDetail(
                ErrorCode(error_raw["code"]),
                error_raw["message"],
                error_raw.get("retryable", False),
                error_raw.get("component", ""),
                error_raw.get("metadata", {}),
            )
        return ExecutionEvidence(
            CorrelationIds(ids["trace_id"], ids["request_id"], ids["task_id"], ids["command_id"]),
            item["action_id"],
            ActionStatus(item["status"]),
            item["source"],
            item.get("observed_state", {}),
            item.get("state_version"),
            datetime.fromisoformat(item["observed_at"]),
            error,
        )
