"""Deterministic sparse router with an inverted index and Top-K gating."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Iterable

from homeclaw.domain import CorrelationIds
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.routing.models import RouteDecision, RouteRequest, SkillDefinition, SkillMatch
from homeclaw.routing.registry import SkillRegistry


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> tuple[str, ...]:
    lowered = text.lower().replace("-", "_")
    tokens = _TOKEN_RE.findall(lowered)
    chinese = [token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    bigrams = [chinese[index] + chinese[index + 1] for index in range(len(chinese) - 1)]
    return tuple(tokens + bigrams)


class SkillRouter:
    def __init__(
        self,
        registry: SkillRegistry,
        *,
        minimum_score: float = 0.12,
        fallback_skill_id: str = "clarification",
        always_exposed_tools: tuple[str, ...] = ("request_clarification",),
        telemetry: Telemetry | None = None,
    ) -> None:
        self.registry = registry
        self.minimum_score = minimum_score
        self.fallback_skill_id = fallback_skill_id
        self.always_exposed_tools = always_exposed_tools
        self.telemetry = telemetry or NoopTelemetry()
        self._skill_tokens: dict[str, Counter[str]] = {}
        self._index: dict[str, set[str]] = defaultdict(set)
        self._document_frequency: Counter[str] = Counter()
        self._build_index()

    def _build_index(self) -> None:
        for skill in self.registry.skills:
            text = " ".join((skill.skill_id, skill.domain, skill.description, *skill.keywords))
            counts = Counter(tokenize(text))
            self._skill_tokens[skill.skill_id] = counts
            for token in counts:
                self._index[token].add(skill.skill_id)
                self._document_frequency[token] += 1

    def route(self, request: RouteRequest) -> RouteDecision:
        ids = request.ids or CorrelationIds()
        with self.telemetry.span(
            "router.retrieve",
            ids,
            {"router.top_k": request.top_k, "router.total_skills": len(self.registry.skills)},
        ) as span:
            decision = self._route(request)
            span.attributes["router.candidates"] = decision.candidate_count
            span.attributes["router.selected"] = len(decision.matches)
            span.attributes["router.exposed_tools"] = len(decision.exposed_tools)
            span.attributes["router.fallback"] = decision.fallback
            return decision

    def _route(self, request: RouteRequest) -> RouteDecision:
        query_tokens = Counter(tokenize(request.text))
        normalized_text = " ".join(request.text.lower().replace("-", " ").split())
        candidate_ids: set[str] = set()
        for token in query_tokens:
            candidate_ids.update(self._index.get(token, ()))

        required_domains = set(request.required_domains)
        if required_domains:
            candidate_ids.update(
                skill.skill_id for skill in self.registry.skills if skill.domain in required_domains
            )

        matches: list[SkillMatch] = []
        for skill_id in candidate_ids:
            skill = self.registry.get_skill(skill_id)
            if skill is None or not skill.available:
                continue
            if skill.activation_phrases and not any(
                phrase.lower() in normalized_text for phrase in skill.activation_phrases
            ):
                continue
            if required_domains and skill.domain not in required_domains:
                continue
            score, terms = self._score(skill, query_tokens)
            if score >= self.minimum_score:
                matches.append(SkillMatch(skill.skill_id, score, terms, skill.domain))

        matches.sort(key=lambda match: (-match.score, match.skill_id))
        selected = matches[: request.top_k]
        fallback = not selected
        if fallback:
            fallback_skill = self.registry.get_skill(self.fallback_skill_id)
            if fallback_skill is not None and fallback_skill.available:
                selected = [
                    SkillMatch(
                        fallback_skill.skill_id,
                        fallback_skill.competence,
                        (),
                        fallback_skill.domain,
                    )
                ]

        tools = set(self.always_exposed_tools)
        resources: set[str] = set()
        for match in selected:
            skill = self.registry.get_skill(match.skill_id)
            if skill is not None:
                tools.update(skill.tool_names)
                resources.update(skill.knowledge_resource_uris)
        tools.intersection_update(tool.name for tool in self.registry.tools)

        return RouteDecision(
            matches=tuple(selected),
            exposed_tools=tuple(sorted(tools)),
            knowledge_resource_uris=tuple(sorted(resources)),
            fallback=fallback,
            candidate_count=len(candidate_ids),
            total_skill_count=len(self.registry.skills),
            total_tool_count=len(self.registry.tools),
        )

    def _score(self, skill: SkillDefinition, query: Counter[str]) -> tuple[float, tuple[str, ...]]:
        document = self._skill_tokens[skill.skill_id]
        overlap = sorted(set(query) & set(document))
        if not overlap:
            return 0.0, ()
        total_skills = max(len(self.registry.skills), 1)
        lexical = 0.0
        for token in overlap:
            inverse_frequency = math.log((total_skills + 1) / (self._document_frequency[token] + 1)) + 1.0
            lexical += min(query[token], document[token]) * inverse_frequency
        normalization = math.sqrt(sum(query.values()) * sum(document.values())) or 1.0
        lexical = min(lexical / normalization, 1.0)
        keyword_tokens = set(tokenize(" ".join(skill.keywords)))
        keyword_coverage = len(set(query) & keyword_tokens) / max(len(set(query)), 1)
        score = 0.70 * lexical + 0.20 * keyword_coverage + 0.10 * skill.competence
        return min(score, 1.0), tuple(overlap)
