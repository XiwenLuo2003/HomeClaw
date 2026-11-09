"""Second-stage tool contraction using anchored device capabilities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from homeclaw.domain import DeviceRef
from homeclaw.routing.models import RouteDecision
from homeclaw.verification.registry import CapabilityRegistry


@dataclass(frozen=True)
class ToolContractionResult:
    decision: RouteDecision
    before_count: int
    after_count: int
    candidate_device_count: int

    @property
    def reduction(self) -> float:
        return 0.0 if self.before_count == 0 else 1.0 - self.after_count / self.before_count


class ToolSpaceContractor:
    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        always_allowed: tuple[str, ...] = ("request_clarification", "get_device_state"),
    ) -> None:
        self.capability_registry = capability_registry
        self.always_allowed = set(always_allowed)

    def contract(
        self,
        route: RouteDecision,
        candidates: Sequence[DeviceRef],
    ) -> ToolContractionResult:
        if not candidates:
            return ToolContractionResult(
                route, len(route.exposed_tools), len(route.exposed_tools), 0
            )
        supported = set(self.always_allowed)
        resolved_count = 0
        for candidate in candidates:
            record = self.capability_registry.get_device(candidate.home_id, candidate.device_id)
            if record is not None:
                supported.update(record.tools)
                resolved_count += 1
        contracted_tools = tuple(sorted(set(route.exposed_tools) & supported))
        contracted = replace(route, exposed_tools=contracted_tools)
        return ToolContractionResult(
            contracted,
            len(route.exposed_tools),
            len(contracted_tools),
            resolved_count,
        )
