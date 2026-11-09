"""Dependency-free TF-IDF vector baseline for comparable Router evaluation."""

from __future__ import annotations

import math
import re
from collections import Counter

from homeclaw.routing import (
    RouteDecision,
    RouteRequest,
    SkillMatch,
    SkillRegistry,
)


_WORD = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]", re.IGNORECASE)


def _terms(text: str) -> tuple[str, ...]:
    raw = tuple(item.lower() for item in _WORD.findall(text))
    cjk = tuple(item for item in raw if len(item) == 1 and "\u3400" <= item <= "\u9fff")
    bigrams = tuple(cjk[index] + cjk[index + 1] for index in range(len(cjk) - 1))
    return raw + bigrams


class TfidfVectorRouter:
    """A deliberately ordinary vector-space baseline, not HomeClaw routing logic."""

    def __init__(self, registry: SkillRegistry, fallback_skill_id: str = "clarification") -> None:
        self.registry = registry
        self.fallback_skill_id = fallback_skill_id
        self._documents: dict[str, Counter[str]] = {}
        document_frequency: Counter[str] = Counter()
        for skill in registry.skills:
            text = " ".join(
                (skill.skill_id, skill.domain, skill.description, *skill.keywords, *skill.activation_phrases)
            )
            counts = Counter(_terms(text))
            self._documents[skill.skill_id] = counts
            document_frequency.update(counts.keys())
        size = max(len(self._documents), 1)
        self._idf = {
            term: math.log((1 + size) / (1 + frequency)) + 1.0
            for term, frequency in document_frequency.items()
        }
        self._vectors = {
            skill_id: self._vector(counts) for skill_id, counts in self._documents.items()
        }

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        total = sum(counts.values()) or 1
        return {
            term: count / total * self._idf.get(term, 1.0)
            for term, count in counts.items()
        }

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        numerator = sum(value * right.get(term, 0.0) for term, value in left.items())
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0

    def route(self, request: RouteRequest) -> RouteDecision:
        query = self._vector(Counter(_terms(request.text)))
        scored = []
        for skill in self.registry.skills:
            if not skill.available:
                continue
            if request.required_domains and skill.domain not in request.required_domains:
                continue
            score = self._cosine(query, self._vectors[skill.skill_id])
            if score > 0:
                scored.append((score, skill.skill_id))
        scored.sort(key=lambda item: (-item[0], item[1]))
        fallback = not scored
        if fallback:
            fallback_skill = self.registry.get_skill(self.fallback_skill_id)
            selected = [(0.0, self.fallback_skill_id)] if fallback_skill is not None else []
        else:
            selected = scored[: request.top_k]
        matches = []
        tools: list[str] = []
        resources: list[str] = []
        for score, skill_id in selected:
            skill = self.registry.get_skill(skill_id)
            if skill is None:
                continue
            matches.append(SkillMatch(skill_id, score, (), skill.domain))
            tools.extend(name for name in skill.tool_names if name not in tools)
            resources.extend(
                uri for uri in skill.knowledge_resource_uris if uri not in resources
            )
        return RouteDecision(
            matches=tuple(matches),
            exposed_tools=tuple(tools),
            knowledge_resource_uris=tuple(resources),
            fallback=fallback,
            candidate_count=len(scored),
            total_skill_count=len(self.registry.skills),
            total_tool_count=len(self.registry.tools),
        )
