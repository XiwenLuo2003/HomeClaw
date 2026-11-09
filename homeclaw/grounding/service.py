"""Device-disambiguation Skill service with topology anchoring and fallback."""

from __future__ import annotations

from typing import Optional

from homeclaw.domain import CorrelationIds, DeviceRef, GroundingCandidate, GroundingResult
from homeclaw.grounding.client import GrounderCandidate, GrounderClient, GrounderRequest
from homeclaw.topology import TopologyCandidateFilter
from homeclaw.observability import NoopTelemetry, Telemetry


class DeviceDisambiguationService:
    def __init__(
        self,
        candidate_filter: TopologyCandidateFilter,
        client: GrounderClient,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.candidate_filter = candidate_filter
        self.client = client
        self.telemetry = telemetry or NoopTelemetry()

    def resolve(
        self,
        *,
        home_id: str,
        image_uri: str,
        query: str,
        room_id: Optional[str] = None,
        capability: Optional[str] = None,
        timeout_seconds: float = 10.0,
        ids: CorrelationIds | None = None,
    ) -> GroundingResult:
        anchors = self.candidate_filter.candidates(room_id=room_id, capability=capability)
        candidates = tuple(
            GrounderCandidate(
                device=DeviceRef(home_id, anchor.device_id, anchor.room_id, capability),
                name=anchor.name,
                aliases=anchor.aliases,
            )
            for anchor in anchors
        )
        if not candidates:
            return GroundingResult(
                query=query,
                candidates=(),
                selected_device_id=None,
                ambiguous=True,
                model_version="knowledge-anchor/no-candidate",
            )
        if len(candidates) == 1:
            only = candidates[0]
            return GroundingResult(
                query=query,
                candidates=(
                    GroundingCandidate(
                        device=only.device,
                        score=1.0,
                        evidence="topology constraints produced one candidate; model call skipped",
                    ),
                ),
                selected_device_id=only.device.device_id,
                ambiguous=False,
                model_version="knowledge-anchor/deterministic",
            )
        try:
            with self.telemetry.span(
                "grounder.infer",
                ids or CorrelationIds(),
                {"grounder.candidate_count": len(candidates)},
            ) as span:
                result = self.client.ground(
                    GrounderRequest(image_uri, query, candidates),
                    timeout_seconds=timeout_seconds,
                )
                span.attributes["grounder.model"] = result.model_version
                span.attributes["grounder.ambiguous"] = result.ambiguous
                span.attributes["grounder.latency_ms"] = result.latency_ms
                return result
        except (OSError, TimeoutError, ValueError) as exc:
            return GroundingResult(
                query=query,
                candidates=tuple(
                    GroundingCandidate(
                        device=item.device,
                        score=0.0,
                        evidence=f"grounder unavailable: {type(exc).__name__}",
                    )
                    for item in candidates
                ),
                selected_device_id=None,
                ambiguous=True,
                model_version="grounder/unavailable",
            )
