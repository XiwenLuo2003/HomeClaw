"""Online-model semantic proposer with strict structured output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from homeclaw.domain import (
    ActionProposal,
    CorrelationIds,
    DeviceRef,
    IdempotencyClass,
    RiskLevel,
)
from homeclaw.llm import BaseLLMClient
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.routing import RouteDecision, SkillRegistry


@dataclass(frozen=True)
class ProposalResult:
    proposals: tuple[ActionProposal, ...]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_text: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Proposer(Protocol):
    def propose(
        self,
        user_input: str,
        route: RouteDecision,
        ids: CorrelationIds,
        *,
        context: Mapping[str, Any] | None = None,
        feedback: Sequence[Mapping[str, Any]] = (),
    ) -> ProposalResult:
        ...


class StaticProposer:
    def __init__(self, proposals: Sequence[ActionProposal]) -> None:
        self.proposals = tuple(proposals)

    def propose(
        self,
        user_input: str,
        route: RouteDecision,
        ids: CorrelationIds,
        *,
        context: Mapping[str, Any] | None = None,
        feedback: Sequence[Mapping[str, Any]] = (),
    ) -> ProposalResult:
        return ProposalResult(self.proposals)


class LLMProposer:
    """Uses GPT/Gemini-compatible BaseLLMClient as the Agent's main model."""

    def __init__(
        self,
        llm: BaseLLMClient,
        registry: SkillRegistry,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.telemetry = telemetry or NoopTelemetry()

    def propose(
        self,
        user_input: str,
        route: RouteDecision,
        ids: CorrelationIds,
        *,
        context: Mapping[str, Any] | None = None,
        feedback: Sequence[Mapping[str, Any]] = (),
    ) -> ProposalResult:
        schemas = [
            {
                "name": name,
                "description": self.registry.get_tool(name).description,
                "input_schema": self.registry.get_tool(name).input_schema,
            }
            for name in route.exposed_tools
            if self.registry.get_tool(name) is not None
        ]
        system = (
            "You are the semantic proposer for a smart-home agent. Use only the supplied tools. "
            "Return strict JSON: {\"actions\":[{\"tool_name\":str,\"home_id\":str,"
            "\"device_id\":str,\"room_id\":str|null,\"arguments\":object,"
            "\"expected_state\":object,\"verification\":object,\"source_skill\":str,"
            "\"idempotency\":str,\"risk\":str}]}. Never claim that an action succeeded."
        )
        user = json.dumps(
            {
                "request": user_input,
                "selected_skills": list(route.selected_skill_ids),
                "tools": schemas,
                "context": dict(context or {}),
                "verifier_feedback": list(feedback),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self.telemetry.span(
            "planner.generate",
            ids,
            {"planner.skill_count": len(route.matches), "planner.tool_count": len(schemas)},
        ) as span:
            response = self.llm.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": user}]
            )
            usage = response.usage or {}
            span.attributes["planner.prompt_tokens"] = int(usage.get("prompt_tokens", 0))
            span.attributes["planner.completion_tokens"] = int(
                usage.get("completion_tokens", 0)
            )
            config = getattr(self.llm, "config", None)
            span.attributes["planner.model"] = getattr(
                config, "model", type(self.llm).__name__
            )
        payload = self._extract_json(response.text)
        proposals = tuple(self._parse_action(item, route) for item in payload.get("actions", []))
        usage = response.usage or {}
        return ProposalResult(
            proposals,
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
            response.text,
        )

    def _parse_action(self, raw: Mapping[str, Any], route: RouteDecision) -> ActionProposal:
        tool_name = str(raw["tool_name"])
        if tool_name not in route.exposed_tools:
            raise ValueError(f"proposer selected tool outside routed tool subset: {tool_name}")
        source_skill = str(raw["source_skill"])
        if source_skill not in route.selected_skill_ids:
            raise ValueError(f"proposer selected skill outside route: {source_skill}")
        return ActionProposal(
            tool_name=tool_name,
            target=DeviceRef(
                home_id=str(raw["home_id"]),
                device_id=str(raw["device_id"]),
                room_id=str(raw["room_id"]) if raw.get("room_id") is not None else None,
            ),
            arguments=dict(raw.get("arguments", {})),
            source_skill=source_skill,
            expected_state=dict(raw["expected_state"]),
            verification=dict(raw.get("verification", {})),
            idempotency=IdempotencyClass(raw.get("idempotency", "idempotent_with_key")),
            risk=RiskLevel(raw.get("risk", "low")),
        )

    @staticmethod
    def _extract_json(text: str) -> Mapping[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
        candidate = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
        if not candidate:
            raise ValueError("proposer did not return a JSON object")
        payload = json.loads(candidate)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("actions"), list):
            raise ValueError("proposer JSON must contain an actions list")
        return payload
