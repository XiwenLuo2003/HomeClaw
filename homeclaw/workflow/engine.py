"""Checkpoint-after-each-node workflow host."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from homeclaw.domain import CorrelationIds, DomainError, ErrorCode, ErrorDetail, TaskStatus
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.workflow.state import ExecutionBudget, WorkflowNode, WorkflowState
from homeclaw.workflow.store import CheckpointStore, OutboxMessage


@dataclass(frozen=True)
class NodeResult:
    next_node: WorkflowNode
    data: Mapping[str, Any] = field(default_factory=dict)
    tokens_used: int = 0
    outbox: tuple[tuple[str, Mapping[str, Any]], ...] = ()
    wait: bool = False

    def __post_init__(self) -> None:
        if self.tokens_used < 0:
            raise ValueError("tokens_used must be non-negative")


class WorkflowNodeHandler(Protocol):
    def __call__(self, state: WorkflowState) -> NodeResult:
        ...


class WorkflowHost:
    def __init__(
        self,
        store: CheckpointStore,
        handlers: Mapping[WorkflowNode, WorkflowNodeHandler],
        budget: ExecutionBudget | None = None,
        telemetry: Telemetry | None = None,
    ) -> None:
        self.store = store
        self.handlers = dict(handlers)
        self.budget = budget or ExecutionBudget()
        self.telemetry = telemetry or NoopTelemetry()

    def start(
        self,
        user_input: str,
        *,
        initial_data: Mapping[str, Any] | None = None,
        ids: CorrelationIds | None = None,
    ) -> WorkflowState:
        state = WorkflowState.create(user_input, self.budget, ids=ids, initial_data=initial_data)
        self.store.create(state)
        return self._run(state)

    def resume(self, task_id: str) -> WorkflowState:
        state = self.store.load(task_id)
        if state is None:
            raise KeyError(task_id)
        if state.current_node.terminal:
            return state
        return self._run(state)

    def _run(self, state: WorkflowState) -> WorkflowState:
        while not state.current_node.terminal:
            if state.expired:
                return self._terminate(
                    state,
                    WorkflowNode.FAIL,
                    TaskStatus.EXPIRED,
                    ErrorDetail(ErrorCode.TIMEOUT, "workflow deadline exceeded", component="workflow"),
                )
            if state.step_count >= self.budget.max_steps:
                return self._terminate(
                    state,
                    WorkflowNode.FAIL,
                    TaskStatus.FAILED,
                    ErrorDetail(
                        ErrorCode.BUDGET_EXHAUSTED,
                        "maximum workflow steps exceeded",
                        component="workflow",
                    ),
                )
            if state.tokens_used > self.budget.max_tokens:
                return self._terminate(
                    state,
                    WorkflowNode.FAIL,
                    TaskStatus.FAILED,
                    ErrorDetail(
                        ErrorCode.BUDGET_EXHAUSTED,
                        "workflow token budget exceeded",
                        component="workflow",
                    ),
                )

            node = state.current_node
            handler = self.handlers.get(node)
            if handler is None:
                return self._terminate(
                    state,
                    WorkflowNode.FAIL,
                    TaskStatus.FAILED,
                    ErrorDetail(
                        ErrorCode.INTERNAL,
                        f"no handler registered for node {node.value}",
                        component="workflow",
                    ),
                )

            state.status = TaskStatus.RUNNING
            try:
                with self.telemetry.span(
                    f"workflow.{node.value}",
                    state.ids,
                    {"workflow.node": node.value, "workflow.step": state.step_count},
                ):
                    result = handler(state)
            except DomainError as exc:
                if exc.detail.retryable:
                    state.status = TaskStatus.WAITING
                    state.errors.append(exc.detail)
                    return self.store.save(state, state.revision)
                return self._terminate(
                    state, WorkflowNode.FAIL, TaskStatus.FAILED, exc.detail
                )
            except Exception as exc:
                return self._terminate(
                    state,
                    WorkflowNode.FAIL,
                    TaskStatus.FAILED,
                    ErrorDetail(
                        ErrorCode.INTERNAL,
                        f"{type(exc).__name__}: {exc}",
                        component=f"workflow.{node.value}",
                    ),
                )

            if node is WorkflowNode.REPLAN:
                state.replan_count += 1
                if state.replan_count > self.budget.max_replans:
                    return self._terminate(
                        state,
                        WorkflowNode.FAIL,
                        TaskStatus.FAILED,
                        ErrorDetail(
                            ErrorCode.BUDGET_EXHAUSTED,
                            "maximum replan count exceeded",
                            component="workflow",
                        ),
                    )

            state.data.update(result.data)
            state.tokens_used += result.tokens_used
            state.step_count += 1
            state.completed_nodes.append(node.value)
            state.current_node = result.next_node
            if result.wait:
                state.status = TaskStatus.WAITING
            elif result.next_node is WorkflowNode.COMPLETE:
                state.status = TaskStatus.SUCCEEDED
            elif result.next_node is WorkflowNode.REJECT:
                state.status = TaskStatus.REJECTED
            elif result.next_node is WorkflowNode.FAIL:
                state.status = TaskStatus.FAILED

            previous_revision = state.revision
            messages = [
                OutboxMessage(task_id=state.ids.task_id, topic=topic, payload=dict(payload))
                for topic, payload in result.outbox
            ]
            state = self.store.save_with_outbox(state, previous_revision, messages)
            if result.wait:
                return state

        return state

    def _terminate(
        self,
        state: WorkflowState,
        node: WorkflowNode,
        status: TaskStatus,
        error: ErrorDetail,
    ) -> WorkflowState:
        state.current_node = node
        state.status = status
        state.errors.append(error)
        return self.store.save(state, state.revision)
