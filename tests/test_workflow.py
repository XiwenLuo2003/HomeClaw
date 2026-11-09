from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from homeclaw.domain import DomainError, ErrorCode, ErrorDetail, TaskStatus
from homeclaw.observability import InMemoryTelemetry
from homeclaw.workflow import (
    CheckpointConflict,
    ExecutionBudget,
    InMemoryCheckpointStore,
    NodeResult,
    OutboxMessage,
    SqliteCheckpointStore,
    WorkflowHost,
    WorkflowNode,
    WorkflowState,
)


class SimulatedProcessCrash(BaseException):
    pass


class WorkflowTests(unittest.TestCase):
    def test_host_checkpoints_each_node_and_emits_outbox(self) -> None:
        store = InMemoryCheckpointStore()
        telemetry = InMemoryTelemetry()
        handlers = {
            WorkflowNode.RECEIVE: lambda state: NodeResult(
                next_node=WorkflowNode.ROUTE,
                data={"normalized": state.user_input.lower()},
            ),
            WorkflowNode.ROUTE: lambda state: NodeResult(
                next_node=WorkflowNode.COMPLETE,
                data={"skills": ["lighting"]},
                tokens_used=12,
                outbox=(("workflow.completed", {"result": "ok"}),),
            ),
        }
        host = WorkflowHost(store, handlers, telemetry=telemetry)

        result = host.start("Turn on the lamp")

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.completed_nodes, ["receive", "route"])
        self.assertEqual(result.revision, 2)
        self.assertEqual(result.tokens_used, 12)
        self.assertEqual(len(store.pending()), 1)
        self.assertEqual([span.name for span in telemetry.spans], ["workflow.receive", "workflow.route"])

    def test_resume_restarts_from_last_durable_node_after_crash(self) -> None:
        store = InMemoryCheckpointStore()
        attempts = {"route": 0}

        def route(state: WorkflowState) -> NodeResult:
            attempts["route"] += 1
            if attempts["route"] == 1:
                raise SimulatedProcessCrash()
            return NodeResult(WorkflowNode.COMPLETE, {"recovered": True})

        host = WorkflowHost(
            store,
            {
                WorkflowNode.RECEIVE: lambda state: NodeResult(WorkflowNode.ROUTE),
                WorkflowNode.ROUTE: route,
            },
        )
        state = WorkflowState.create("recover me", host.budget)
        store.create(state)

        with self.assertRaises(SimulatedProcessCrash):
            host.resume(state.ids.task_id)

        durable = store.load(state.ids.task_id)
        self.assertIsNotNone(durable)
        self.assertEqual(durable.current_node, WorkflowNode.ROUTE)
        result = host.resume(state.ids.task_id)
        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertTrue(result.data["recovered"])

    def test_every_runtime_node_can_resume_from_its_last_checkpoint(self) -> None:
        sequence = (
            WorkflowNode.RECEIVE,
            WorkflowNode.GROUND,
            WorkflowNode.ROUTE,
            WorkflowNode.PLAN,
            WorkflowNode.VERIFY,
            WorkflowNode.EXECUTE,
            WorkflowNode.CONFIRM,
        )
        for crash_node in sequence:
            with self.subTest(crash_node=crash_node.value):
                store = InMemoryCheckpointStore()
                attempts = {node: 0 for node in sequence}
                handlers = {}
                for index, node in enumerate(sequence):
                    next_node = (
                        sequence[index + 1]
                        if index + 1 < len(sequence)
                        else WorkflowNode.COMPLETE
                    )

                    def handler(state, *, current=node, following=next_node):
                        attempts[current] += 1
                        if current is crash_node and attempts[current] == 1:
                            raise SimulatedProcessCrash()
                        return NodeResult(following)

                    handlers[node] = handler
                host = WorkflowHost(store, handlers)
                state = WorkflowState.create("recover every node", host.budget)
                store.create(state)

                with self.assertRaises(SimulatedProcessCrash):
                    host.resume(state.ids.task_id)

                durable = store.load(state.ids.task_id)
                self.assertEqual(durable.current_node, crash_node)
                completed = host.resume(state.ids.task_id)
                self.assertEqual(completed.status, TaskStatus.SUCCEEDED)
                self.assertEqual(attempts[crash_node], 2)

    def test_step_budget_terminates_loop(self) -> None:
        store = InMemoryCheckpointStore()
        host = WorkflowHost(
            store,
            {WorkflowNode.RECEIVE: lambda state: NodeResult(WorkflowNode.RECEIVE)},
            budget=ExecutionBudget(max_steps=2),
        )

        result = host.start("loop forever")

        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.errors[-1].code, ErrorCode.BUDGET_EXHAUSTED)

    def test_waiting_workflow_can_resume_from_persisted_node(self) -> None:
        store = InMemoryCheckpointStore()
        calls = {"confirm": 0}

        def wait_for_confirmation(state):
            calls["confirm"] += 1
            if calls["confirm"] == 1:
                return NodeResult(WorkflowNode.CONFIRM, {"waiting_for": "device-state"}, wait=True)
            return NodeResult(WorkflowNode.COMPLETE, {"confirmed": True})

        host = WorkflowHost(
            store,
            {
                WorkflowNode.RECEIVE: lambda state: NodeResult(WorkflowNode.CONFIRM),
                WorkflowNode.CONFIRM: wait_for_confirmation,
            },
        )

        waiting = host.start("wait for device")
        self.assertEqual(waiting.status, TaskStatus.WAITING)
        self.assertEqual(waiting.current_node, WorkflowNode.CONFIRM)

        resumed = host.resume(waiting.ids.task_id)
        self.assertEqual(resumed.status, TaskStatus.SUCCEEDED)
        self.assertTrue(resumed.data["confirmed"])

    def test_retryable_domain_error_pauses_at_same_node_then_resumes(self) -> None:
        store = InMemoryCheckpointStore()
        calls = {"count": 0}

        def transient(state):
            calls["count"] += 1
            if calls["count"] == 1:
                raise DomainError(
                    ErrorDetail(
                        ErrorCode.DEPENDENCY_UNAVAILABLE,
                        "model temporarily unavailable",
                        retryable=True,
                        component="planner",
                    )
                )
            return NodeResult(WorkflowNode.COMPLETE)

        host = WorkflowHost(store, {WorkflowNode.RECEIVE: transient})
        waiting = host.start("retry later")
        self.assertEqual(waiting.status, TaskStatus.WAITING)
        self.assertEqual(waiting.current_node, WorkflowNode.RECEIVE)

        completed = host.resume(waiting.ids.task_id)
        self.assertEqual(completed.status, TaskStatus.SUCCEEDED)

    def test_unexpected_node_exception_becomes_auditable_failed_state(self) -> None:
        host = WorkflowHost(
            InMemoryCheckpointStore(),
            {WorkflowNode.RECEIVE: lambda state: (_ for _ in ()).throw(ValueError("bad payload"))},
        )
        result = host.start("fail safely")
        self.assertEqual(result.status, TaskStatus.FAILED)
        self.assertEqual(result.errors[-1].code, ErrorCode.INTERNAL)
        self.assertIn("ValueError", result.errors[-1].message)

    def test_optimistic_revision_rejects_stale_writer(self) -> None:
        store = InMemoryCheckpointStore()
        state = WorkflowState.create("concurrent", ExecutionBudget())
        store.create(state)
        first = store.load(state.ids.task_id)
        stale = store.load(state.ids.task_id)
        self.assertIsNotNone(first)
        self.assertIsNotNone(stale)

        store.save(first, expected_revision=0)
        with self.assertRaises(CheckpointConflict):
            store.save(stale, expected_revision=0)

    def test_sqlite_checkpoint_and_outbox_survive_reopen(self) -> None:
        local_tmp = Path(__file__).resolve().parents[1] / "tmp"
        local_tmp.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_tmp) as directory:
            path = Path(directory) / "workflow.db"
            with SqliteCheckpointStore(path) as store:
                state = WorkflowState.create("persist me", ExecutionBudget())
                store.create(state)
                state.data["value"] = 42
                saved = store.save(state, 0)
                message = OutboxMessage(saved.ids.task_id, "task.changed", {"revision": 1})
                store.enqueue(message)

            with SqliteCheckpointStore(path) as reopened:
                loaded = reopened.load(saved.ids.task_id)

                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.data["value"], 42)
                self.assertEqual(reopened.pending()[0].message_id, message.message_id)
                reopened.mark_published(message.message_id)
                self.assertEqual(reopened.pending(), [])


if __name__ == "__main__":
    unittest.main()
