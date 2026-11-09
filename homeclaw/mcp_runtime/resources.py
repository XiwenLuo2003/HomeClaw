"""Aggregated MCP state Resources with selective update notifications."""

from __future__ import annotations

from typing import Callable, Mapping, Optional

from homeclaw.mcp_runtime.server import DomainMCPServer, MCPResource
from homeclaw.state import ApplyResult, InMemoryStateCache, StateSnapshot, VersionedStateDiff


class StateResourcePublisher:
    def __init__(
        self,
        server: DomainMCPServer,
        cache: InMemoryStateCache,
        *,
        should_notify: Callable[[Optional[StateSnapshot], StateSnapshot], bool],
    ) -> None:
        self.server = server
        self.cache = cache
        self.should_notify = should_notify
        self._registered: set[tuple[str, str]] = set()

    @staticmethod
    def uri(home_id: str, device_id: str) -> str:
        return f"home://{home_id}/devices/{device_id}/state"

    def register(self, home_id: str, device_id: str, name: str) -> str:
        key = (home_id, device_id)
        if key in self._registered:
            return self.uri(home_id, device_id)
        uri = self.uri(home_id, device_id)

        def read() -> Mapping[str, object]:
            snapshot = self.cache.get(home_id, device_id, allow_stale=True)
            if snapshot is None:
                return {"available": False, "stale": True}
            return {
                "available": True,
                "stale": snapshot.stale,
                "sequence": snapshot.sequence,
                "observed_at": snapshot.observed_at.isoformat(),
                "state": dict(snapshot.state),
            }

        self.server.register_resource(
            MCPResource(uri, name, "Aggregated device state; not a raw sensor event stream", read)
        )
        self._registered.add(key)
        return uri

    def apply(self, diff: VersionedStateDiff) -> ApplyResult:
        previous = self.cache.get(diff.home_id, diff.device_id, allow_stale=True)
        result = self.cache.apply(diff)
        current = self.cache.get(diff.home_id, diff.device_id, allow_stale=True)
        key = (diff.home_id, diff.device_id)
        if (
            result is ApplyResult.APPLIED
            and current is not None
            and key in self._registered
            and self.should_notify(previous, current)
        ):
            self.server.notify_resource_updated(self.uri(*key))
        return result
