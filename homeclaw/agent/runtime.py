"""Composition root for Workflow -> Router -> Proposer -> Verifier -> MCP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Protocol, Sequence

from homeclaw.agent.proposer import Proposer
from homeclaw.agent.binder import InstanceBinder
from homeclaw.domain import (
    ActionProposal,
    ActionStatus,
    CorrelationIds,
    DeviceRef,
    ErrorCode,
    ErrorDetail,
    ExecutionEvidence,
    IdempotencyClass,
    RiskLevel,
)
from homeclaw.mcp_runtime import MCPHostGateway
from homeclaw.security import Principal
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.routing import RouteDecision, RouteRequest, SkillRouter, ToolSpaceContractor
from homeclaw.resilience import AdaptiveTopKPolicy
from homeclaw.verification import ActionConflictDetector, ActionVerifier
from homeclaw.workflow import (
    CheckpointStore,
    ExecutionBudget,
    NodeResult,
    WorkflowHost,
    WorkflowNode,
    WorkflowState,
)
from homeclaw.workflow.action_attempts import PostgresActionAttemptStore
from homeclaw.grounding import DeviceDisambiguationService


def _proposal_from_dict(raw: Mapping[str, Any]) -> ActionProposal:
    target = raw["target"]
    return ActionProposal(
        tool_name=raw["tool_name"],
        target=DeviceRef(
            target["home_id"], target["device_id"], target.get("room_id"), target.get("capability")
        ),
        arguments=dict(raw["arguments"]),
        source_skill=raw["source_skill"],
        expected_state=dict(raw["expected_state"]),
        preconditions=tuple(raw.get("preconditions", ())),
        verification=dict(raw.get("verification", {})),
        idempotency=IdempotencyClass(raw["idempotency"]),
        risk=RiskLevel(raw["risk"]),
        action_id=raw["action_id"],
    )


class ActionDispatcher(Protocol):
    def execute(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds,
        allowed_tools: Sequence[str],
    ) -> ExecutionEvidence:
        ...


class MCPActionDispatcher:
    def __init__(
        self,
        gateway: MCPHostGateway,
        *,
        principal: Principal | None = None,
        policy_version: str | None = None,
        confirmation: Callable[[ActionProposal], bool] | None = None,
    ) -> None:
        self.gateway = gateway
        self.principal = principal
        self.policy_version = policy_version
        self.confirmation = confirmation or (lambda proposal: False)

    def execute(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds,
        allowed_tools: Sequence[str],
    ) -> ExecutionEvidence:
        arguments = {
            "home_id": proposal.target.home_id,
            "device_id": proposal.target.device_id,
            **dict(proposal.arguments),
        }
        arguments["_homeclaw_action_id"] = proposal.action_id
        raw = self.gateway.call(
            proposal.tool_name,
            arguments,
            ids,
            allowed_tools=allowed_tools,
            principal=self.principal,
            policy_version=self.policy_version,
            confirmed=self.confirmation(proposal),
        )
        error_raw = raw.get("error")
        error = None
        if isinstance(error_raw, Mapping):
            error = ErrorDetail(
                code=ErrorCode(error_raw["code"]),
                message=str(error_raw["message"]),
                retryable=bool(error_raw.get("retryable", False)),
                component=str(error_raw.get("component", "")),
                metadata=dict(error_raw.get("metadata", {})),
            )
        return ExecutionEvidence(
            ids=ids,
            action_id=proposal.action_id,
            status=ActionStatus(raw["status"]),
            source=str(raw.get("source", "mcp")),
            observed_state=dict(raw.get("observed_state", {})),
            state_version=raw.get("state_version"),
            error=error,
        )


def _evidence_from_dict(raw: Mapping[str, Any]) -> ExecutionEvidence:
    ids = raw["ids"]
    error_raw = raw.get("error")
    error = None
    if isinstance(error_raw, Mapping):
        error = ErrorDetail(
            ErrorCode(error_raw["code"]),
            str(error_raw["message"]),
            bool(error_raw.get("retryable", False)),
            str(error_raw.get("component", "")),
            dict(error_raw.get("metadata", {})),
        )
    return ExecutionEvidence(
        CorrelationIds(
            ids["trace_id"], ids["request_id"], ids["task_id"], ids.get("command_id")
        ),
        str(raw["action_id"]),
        ActionStatus(raw["status"]),
        str(raw["source"]),
        dict(raw.get("observed_state", {})),
        raw.get("state_version"),
        datetime.fromisoformat(str(raw["observed_at"])),
        error=error,
    )


class DurableActionDispatcher:
    """Makes workflow replay reuse the original command and idempotency key."""

    def __init__(self, inner: ActionDispatcher, attempts: PostgresActionAttemptStore) -> None:
        self.inner = inner
        self.attempts = attempts

    def execute(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds,
        allowed_tools: Sequence[str],
    ) -> ExecutionEvidence:
        key = f"{ids.task_id}:{proposal.action_id}"
        claimed = self.attempts.claim(ids, proposal, idempotency_key=key)
        execution_ids = ids
        if not claimed:
            existing = self.attempts.get_by_idempotency_key(key)
            if existing is None:
                raise RuntimeError("idempotency claim was lost without an action-attempt record")
            if existing.evidence is not None:
                return _evidence_from_dict(existing.evidence)
            execution_ids = CorrelationIds(
                ids.trace_id,
                ids.request_id,
                ids.task_id,
                existing.command_id,
            )
            self.attempts.record_retry(existing.command_id)
        evidence = self.inner.execute(proposal, execution_ids, allowed_tools)
        self.attempts.complete(evidence)
        return evidence


class ProductionRuntime:
    def __init__(
        self,
        *,
        store: CheckpointStore,
        router: SkillRouter,
        proposer: Proposer,
        verifier: ActionVerifier,
        dispatcher: ActionDispatcher,
        budget: ExecutionBudget | None = None,
        telemetry: Telemetry | None = None,
        tool_contractor: ToolSpaceContractor | None = None,
        binder: InstanceBinder | None = None,
        attempt_store: PostgresActionAttemptStore | None = None,
        top_k_policy: AdaptiveTopKPolicy | None = None,
        grounder: DeviceDisambiguationService | None = None,
    ) -> None:
        self.router = router
        self.proposer = proposer
        self.verifier = verifier
        self.dispatcher = (
            DurableActionDispatcher(dispatcher, attempt_store)
            if attempt_store is not None
            else dispatcher
        )
        self.conflicts = ActionConflictDetector()
        self.budget = budget or ExecutionBudget()
        self.telemetry = telemetry or NoopTelemetry()
        self.tool_contractor = tool_contractor
        self.binder = binder
        self.top_k_policy = top_k_policy or AdaptiveTopKPolicy()
        self.grounder = grounder
        self.host = WorkflowHost(
            store,
            {
                WorkflowNode.RECEIVE: self._receive,
                WorkflowNode.ROUTE: self._route,
                WorkflowNode.GROUND: self._ground,
                WorkflowNode.PLAN: self._plan,
                WorkflowNode.VERIFY: self._verify,
                WorkflowNode.REPLAN: self._replan,
                WorkflowNode.EXECUTE: self._execute,
                WorkflowNode.CONFIRM: self._confirm,
            },
            budget=self.budget,
            telemetry=self.telemetry,
        )

    def execute(self, user_input: str, *, context: Mapping[str, Any] | None = None) -> WorkflowState:
        ids = CorrelationIds()
        with self.telemetry.span(
            "agent.request",
            ids,
            {"agent.input_length": len(user_input)},
        ) as span:
            state = self.host.start(
                user_input,
                initial_data={"context": dict(context or {})},
                ids=ids,
            )
            span.attributes["agent.status"] = state.status.value
            span.attributes["agent.steps"] = state.step_count
            span.attributes["agent.tokens"] = state.tokens_used
            return state

    def resume(self, task_id: str) -> WorkflowState:
        return self.host.resume(task_id)

    @staticmethod
    def _receive(state: WorkflowState) -> NodeResult:
        return NodeResult(WorkflowNode.ROUTE, {"normalized_input": state.user_input.strip()})

    def _route(self, state: WorkflowState) -> NodeResult:
        top_k = self.top_k_policy.choose(
            state.user_input,
            available_experts=len(self.router.registry.skills),
            token_budget=max(0, self.budget.max_tokens - state.tokens_used),
        )
        decision = self.router.route(RouteRequest(state.user_input, top_k=top_k, ids=state.ids))
        contraction_data = None
        candidate_payloads = state.data.get("context", {}).get("candidate_devices", ())
        if self.tool_contractor is not None and candidate_payloads:
            candidates = tuple(
                DeviceRef(
                    item["home_id"],
                    item["device_id"],
                    item.get("room_id"),
                    item.get("capability"),
                )
                for item in candidate_payloads
            )
            contracted = self.tool_contractor.contract(decision, candidates)
            decision = contracted.decision
            contraction_data = {
                "before_count": contracted.before_count,
                "after_count": contracted.after_count,
                "candidate_device_count": contracted.candidate_device_count,
                "reduction": contracted.reduction,
            }
        next_node = (
            WorkflowNode.GROUND
            if "device-disambiguation" in decision.selected_skill_ids
            else WorkflowNode.PLAN
        )
        return NodeResult(
            next_node,
            {
                "route": {
                    "skills": list(decision.selected_skill_ids),
                    "tools": list(decision.exposed_tools),
                    "resources": list(decision.knowledge_resource_uris),
                    "fallback": decision.fallback,
                    "top_k": top_k,
                },
                "tool_contraction": contraction_data,
            },
        )

    def _ground(self, state: WorkflowState) -> NodeResult:
        context = dict(state.data.get("context", {}))
        image_uri = str(context.get("image_uri", "")).strip()
        home_id = str(context.get("home_id", "")).strip()
        if self.grounder is None or not image_uri or not home_id:
            return NodeResult(
                WorkflowNode.REJECT,
                {
                    "reason": "visual grounding requires configured Grounder, home_id, and image_uri",
                    "grounding": {"ambiguous": True, "error": "missing_grounding_context"},
                },
            )
        result = self.grounder.resolve(
            home_id=home_id,
            image_uri=image_uri,
            query=state.user_input,
            room_id=context.get("room_id"),
            capability=context.get("capability"),
            timeout_seconds=float(context.get("grounder_timeout_seconds", 10.0)),
            ids=state.ids,
        )
        if result.ambiguous or result.selected_device_id is None:
            return NodeResult(
                WorkflowNode.REJECT,
                {
                    "reason": "visual device reference remains ambiguous",
                    "grounding": result.to_dict(),
                },
            )
        selected = next(
            item for item in result.candidates if item.device.device_id == result.selected_device_id
        )
        context["candidate_devices"] = [selected.device.to_dict()]
        context["grounding"] = result.to_dict()
        route = dict(state.data["route"])
        route["tools"] = [
            name for name in route["tools"] if name != "ground_visual_device"
        ]
        return NodeResult(
            WorkflowNode.PLAN,
            {"context": context, "grounding": result.to_dict(), "route": route},
        )

    def _decision(self, state: WorkflowState) -> RouteDecision:
        route = state.data["route"]
        from homeclaw.routing import SkillMatch

        matches = tuple(
            SkillMatch(skill_id, 1.0, (), self.router.registry.get_skill(skill_id).domain)
            for skill_id in route["skills"]
        )
        return RouteDecision(
            matches,
            tuple(route["tools"]),
            tuple(route["resources"]),
            bool(route["fallback"]),
            len(matches),
            len(self.router.registry.skills),
            len(self.router.registry.tools),
        )

    def _plan(self, state: WorkflowState) -> NodeResult:
        result = self.proposer.propose(
            state.user_input,
            self._decision(state),
            state.ids,
            context=state.data.get("context", {}),
            feedback=state.data.get("verifier_feedback", ()),
        )
        if not result.proposals:
            return NodeResult(WorkflowNode.REJECT, {"reason": "proposer returned no actions"})
        return NodeResult(
            WorkflowNode.VERIFY,
            {"proposals": [proposal.to_dict() for proposal in result.proposals]},
            tokens_used=result.total_tokens,
        )

    def _verify(self, state: WorkflowState) -> NodeResult:
        proposals = [_proposal_from_dict(item) for item in state.data["proposals"]]
        feedback: list[dict[str, Any]] = []
        bound_proposals: list[ActionProposal] = []
        for proposal in proposals:
            if self.binder is not None:
                binding = self.binder.bind(proposal, state.ids)
                if not binding.bound:
                    feedback.append(
                        {
                            "code": binding.issue_code,
                            "message": binding.message,
                            "candidate_device_ids": list(binding.candidate_device_ids),
                        }
                    )
                    continue
                proposal = binding.proposal
                assert proposal is not None
            bound_proposals.append(proposal)
            decision = self.verifier.verify(proposal, ids=state.ids)
            feedback.extend(issue.__dict__ for issue in decision.issues)
        feedback.extend(issue.__dict__ for issue in self.conflicts.detect(bound_proposals))
        if feedback:
            return NodeResult(WorkflowNode.REPLAN, {"verifier_feedback": feedback})
        return NodeResult(
            WorkflowNode.EXECUTE,
            {
                "verifier_feedback": [],
                "proposals": [proposal.to_dict() for proposal in bound_proposals],
            },
        )

    @staticmethod
    def _replan(state: WorkflowState) -> NodeResult:
        return NodeResult(WorkflowNode.PLAN)

    def _execute(self, state: WorkflowState) -> NodeResult:
        proposals = [_proposal_from_dict(item) for item in state.data["proposals"]]
        allowed_tools = tuple(state.data["route"]["tools"])
        evidence = []
        for proposal in proposals:
            command_ids = state.ids.for_command()
            item = self.dispatcher.execute(proposal, command_ids, allowed_tools)
            evidence.append(item.to_dict())
        return NodeResult(WorkflowNode.CONFIRM, {"execution_evidence": evidence})

    def _confirm(self, state: WorkflowState) -> NodeResult:
        evidence = state.data.get("execution_evidence", [])
        if evidence and all(item["status"] == ActionStatus.SUCCEEDED.value for item in evidence):
            return NodeResult(
                WorkflowNode.COMPLETE,
                outbox=(("workflow.completed", {"task_id": state.ids.task_id}),),
            )
        failures = [
            {
                "code": "execution_not_confirmed",
                "message": f"action ended in {item.get('status', 'missing')} state",
            }
            for item in evidence
            if item.get("status") != ActionStatus.SUCCEEDED.value
        ]
        if state.replan_count < self.budget.max_replans:
            return NodeResult(WorkflowNode.REPLAN, {"verifier_feedback": failures})
        return NodeResult(WorkflowNode.FAIL, {"execution_failures": failures})
