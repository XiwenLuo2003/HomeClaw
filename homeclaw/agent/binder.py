"""Instance binding between semantic proposals and deterministic verification."""

from __future__ import annotations

from dataclasses import dataclass, replace

from homeclaw.domain import ActionProposal, CorrelationIds, DeviceRef
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.topology import TopologyCandidateFilter
from homeclaw.verification.registry import CapabilityRegistry


@dataclass(frozen=True)
class BindingResult:
    proposal: ActionProposal | None
    candidate_device_ids: tuple[str, ...]
    issue_code: str = ""
    message: str = ""

    @property
    def bound(self) -> bool:
        return self.proposal is not None


class InstanceBinder:
    def __init__(
        self,
        topology_filter: TopologyCandidateFilter,
        capability_registry: CapabilityRegistry,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.topology_filter = topology_filter
        self.capability_registry = capability_registry
        self.telemetry = telemetry or NoopTelemetry()

    def bind(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds | None = None,
    ) -> BindingResult:
        with self.telemetry.span(
            "binder.resolve",
            ids or CorrelationIds(),
            {"binder.target": proposal.target.device_id},
        ):
            exact = self.capability_registry.get_device(
                proposal.target.home_id, proposal.target.device_id
            )
            if exact is not None:
                return BindingResult(proposal, (proposal.target.device_id,))

            anchors = self.topology_filter.candidates(
                room_id=proposal.target.room_id,
                capability=proposal.target.capability,
                text_hint=proposal.target.device_id,
            )
            candidate_ids = tuple(anchor.device_id for anchor in anchors)
            registered = tuple(
                anchor
                for anchor in anchors
                if self.capability_registry.get_device(
                    proposal.target.home_id, anchor.device_id
                )
                is not None
            )
            if len(registered) == 1:
                anchor = registered[0]
                target = DeviceRef(
                    proposal.target.home_id,
                    anchor.device_id,
                    anchor.room_id,
                    proposal.target.capability,
                )
                return BindingResult(replace(proposal, target=target), (anchor.device_id,))
            if not registered:
                return BindingResult(
                    None,
                    candidate_ids,
                    "binding_not_found",
                    f"no registered device matches {proposal.target.device_id}",
                )
            return BindingResult(
                None,
                tuple(anchor.device_id for anchor in registered),
                "binding_ambiguous",
                f"multiple registered devices match {proposal.target.device_id}",
            )
