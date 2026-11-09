"""Typed models for capability-level routing and tool contraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from homeclaw.domain import CorrelationIds


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    risk: str = "low"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.description.strip():
            raise ValueError("tool name and description are required")


@dataclass(frozen=True)
class SkillDefinition:
    skill_id: str
    domain: str
    description: str
    keywords: tuple[str, ...]
    tool_names: tuple[str, ...]
    knowledge_resource_uris: tuple[str, ...] = ()
    activation_phrases: tuple[str, ...] = ()
    competence: float = 0.5
    available: bool = True
    version: str = "1"

    def __post_init__(self) -> None:
        if not self.skill_id.strip() or not self.domain.strip() or not self.description.strip():
            raise ValueError("skill id, domain, and description are required")
        if not self.tool_names:
            raise ValueError("skill must expose at least one tool")
        if self.competence < 0.0 or self.competence > 1.0:
            raise ValueError("skill competence must be in [0, 1]")


@dataclass(frozen=True)
class RouteRequest:
    text: str
    top_k: int = 2
    required_domains: tuple[str, ...] = ()
    ids: Optional[CorrelationIds] = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("route request text must not be empty")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")


@dataclass(frozen=True)
class SkillMatch:
    skill_id: str
    score: float
    matched_terms: tuple[str, ...]
    domain: str


@dataclass(frozen=True)
class RouteDecision:
    matches: Sequence[SkillMatch]
    exposed_tools: tuple[str, ...]
    knowledge_resource_uris: tuple[str, ...]
    fallback: bool
    candidate_count: int
    total_skill_count: int
    total_tool_count: int

    @property
    def selected_skill_ids(self) -> tuple[str, ...]:
        return tuple(match.skill_id for match in self.matches)

    @property
    def tool_contraction_ratio(self) -> float:
        if self.total_tool_count == 0:
            return 0.0
        return 1.0 - len(self.exposed_tools) / self.total_tool_count
