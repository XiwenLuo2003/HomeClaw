"""Deterministic verifier isolated from proposer reasoning."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Mapping

from homeclaw.domain import (
    ActionProposal,
    CorrelationIds,
    IdempotencyClass,
    RiskLevel,
    VerificationDecision,
    VerificationIssue,
)
from homeclaw.domain.models import utc_now
from homeclaw.verification.registry import CapabilityRegistry, ToolSpec
from homeclaw.observability import NoopTelemetry, Telemetry


@dataclass(frozen=True)
class VerificationContext:
    authorized_risk: RiskLevel = RiskLevel.LOW
    max_state_age_seconds: float = 60.0
    facts: Mapping[str, Any] = field(default_factory=dict)


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class ActionVerifier:
    def __init__(self, registry: CapabilityRegistry, telemetry: Telemetry | None = None) -> None:
        self.registry = registry
        self.telemetry = telemetry or NoopTelemetry()

    def verify(
        self,
        proposal: ActionProposal,
        context: VerificationContext | None = None,
        ids: CorrelationIds | None = None,
    ) -> VerificationDecision:
        correlation = ids or CorrelationIds()
        with self.telemetry.span(
            "verifier.check",
            correlation,
            {"verifier.tool": proposal.tool_name, "verifier.device_id": proposal.target.device_id},
        ) as span:
            decision = self._verify(proposal, context)
            span.attributes["verifier.accepted"] = decision.accepted
            span.attributes["verifier.issue_count"] = len(decision.issues)
            return decision

    def _verify(
        self,
        proposal: ActionProposal,
        context: VerificationContext | None = None,
    ) -> VerificationDecision:
        context = context or VerificationContext()
        issues: list[VerificationIssue] = []
        record = self.registry.get_device(proposal.target.home_id, proposal.target.device_id)
        if record is None:
            issues.append(
                VerificationIssue(
                    code="device_not_found",
                    message=f"device {proposal.target.device_id} is not registered",
                    rule="registry.device_exists",
                )
            )
            return self._decision(issues)

        if not record.online:
            issues.append(
                VerificationIssue(
                    code="device_offline",
                    message=f"device {proposal.target.device_id} is offline",
                    rule="registry.device_online",
                    retryable=True,
                )
            )

        tool = record.tools.get(proposal.tool_name)
        if tool is None:
            issues.append(
                VerificationIssue(
                    code="capability_not_found",
                    message=f"tool {proposal.tool_name} is not registered for the device",
                    rule="registry.tool_allowed",
                )
            )
        else:
            issues.extend(self._validate_tool(proposal, tool, context))

        age = utc_now() - record.state_observed_at
        if age > timedelta(seconds=context.max_state_age_seconds):
            issues.append(
                VerificationIssue(
                    code="stale_state",
                    message=f"device state is {age.total_seconds():.1f}s old",
                    rule="state.freshness",
                    retryable=True,
                    metadata={"age_seconds": age.total_seconds()},
                )
            )

        return self._decision(issues)

    def _validate_tool(
        self,
        proposal: ActionProposal,
        tool: ToolSpec,
        context: VerificationContext,
    ) -> list[VerificationIssue]:
        issues: list[VerificationIssue] = []
        unknown = set(proposal.arguments) - set(tool.parameters)
        if unknown:
            issues.append(
                VerificationIssue(
                    code="unknown_parameter",
                    message=f"unknown parameters: {sorted(unknown)}",
                    rule="schema.no_unknown_parameters",
                )
            )
        for name, spec in tool.parameters.items():
            if spec.required and name not in proposal.arguments:
                issues.append(
                    VerificationIssue(
                        code="missing_parameter",
                        message=f"missing required parameter: {name}",
                        rule="schema.required_parameters",
                    )
                )
                continue
            if name in proposal.arguments:
                error = spec.validate(proposal.arguments[name])
                if error:
                    issues.append(
                        VerificationIssue(
                            code="invalid_parameter",
                            message=error,
                            rule="schema.parameter_type_and_range",
                        )
                    )

        if proposal.idempotency is not tool.idempotency:
            issues.append(
                VerificationIssue(
                    code="idempotency_mismatch",
                    message="proposal idempotency does not match registry",
                    rule="execution.idempotency_contract",
                )
            )
        effective_risk = max(proposal.risk, tool.risk, key=lambda risk: _RISK_ORDER[risk])
        if _RISK_ORDER[effective_risk] > _RISK_ORDER[context.authorized_risk]:
            issues.append(
                VerificationIssue(
                    code="risk_not_authorized",
                    message=f"{effective_risk.value} risk action is not authorized",
                    rule="policy.risk_authorization",
                )
            )
        return issues

    def _decision(self, issues: list[VerificationIssue]) -> VerificationDecision:
        return VerificationDecision(
            accepted=not issues,
            issues=tuple(issues),
            registry_version=self.registry.version,
        )
