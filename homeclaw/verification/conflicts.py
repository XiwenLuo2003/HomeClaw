"""Static conflict detection for a proposed atomic-action batch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from homeclaw.domain import ActionProposal


@dataclass(frozen=True)
class ConflictIssue:
    code: str
    message: str
    action_ids: tuple[str, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ActionConflictDetector:
    def detect(
        self,
        actions: Sequence[ActionProposal],
        dependencies: Mapping[str, Sequence[str]] | None = None,
    ) -> tuple[ConflictIssue, ...]:
        dependencies = dependencies or {}
        issues: list[ConflictIssue] = []
        issues.extend(self._duplicates_and_device_conflicts(actions))
        issues.extend(self._environment_conflicts(actions))
        issues.extend(self._resource_conflicts(actions, dependencies))
        issues.extend(self._blocked_actions(actions))
        cycle = self._dependency_cycle(actions, dependencies)
        if cycle:
            issues.append(
                ConflictIssue(
                    "dependency_cycle",
                    "action dependency graph contains a cycle",
                    tuple(cycle),
                )
            )
        return tuple(issues)

    @staticmethod
    def _duplicates_and_device_conflicts(
        actions: Sequence[ActionProposal],
    ) -> list[ConflictIssue]:
        issues: list[ConflictIssue] = []
        for index, left in enumerate(actions):
            for right in actions[index + 1 :]:
                if left.target.device_id != right.target.device_id:
                    continue
                if left.tool_name == right.tool_name and dict(left.arguments) == dict(right.arguments):
                    issues.append(
                        ConflictIssue(
                            "redundant_action",
                            "two actions have the same target, tool, and arguments",
                            (left.action_id, right.action_id),
                        )
                    )
                    continue
                conflicting_fields = [
                    key
                    for key in set(left.expected_state) & set(right.expected_state)
                    if left.expected_state[key] != right.expected_state[key]
                ]
                if conflicting_fields:
                    issues.append(
                        ConflictIssue(
                            "device_conflict",
                            "actions require incompatible final states on the same device",
                            (left.action_id, right.action_id),
                            {"fields": sorted(conflicting_fields)},
                        )
                    )
        return issues

    @staticmethod
    def _environment_conflicts(actions: Sequence[ActionProposal]) -> list[ConflictIssue]:
        effects: dict[str, tuple[Any, str]] = {}
        issues: list[ConflictIssue] = []
        for action in actions:
            current = action.verification.get("environment_effects", {})
            if not isinstance(current, Mapping):
                continue
            for variable, value in current.items():
                previous = effects.get(str(variable))
                if previous is not None and previous[0] != value:
                    issues.append(
                        ConflictIssue(
                            "environment_conflict",
                            f"actions have opposing effects on {variable}",
                            (previous[1], action.action_id),
                            {"variable": variable},
                        )
                    )
                else:
                    effects[str(variable)] = (value, action.action_id)
        return issues

    @staticmethod
    def _resource_conflicts(
        actions: Sequence[ActionProposal], dependencies: Mapping[str, Sequence[str]]
    ) -> list[ConflictIssue]:
        issues: list[ConflictIssue] = []
        resources: dict[str, str] = {}
        for action in actions:
            current = action.verification.get("exclusive_resources", ())
            if not isinstance(current, (list, tuple)):
                continue
            for resource in current:
                resource = str(resource)
                previous = resources.get(resource)
                ordered = previous in dependencies.get(action.action_id, ()) or action.action_id in dependencies.get(previous or "", ())
                if previous is not None and not ordered:
                    issues.append(
                        ConflictIssue(
                            "resource_conflict",
                            f"unordered actions require exclusive resource {resource}",
                            (previous, action.action_id),
                            {"resource": resource},
                        )
                    )
                else:
                    resources[resource] = action.action_id
        return issues

    @staticmethod
    def _blocked_actions(actions: Sequence[ActionProposal]) -> list[ConflictIssue]:
        final_states = {
            action.target.device_id: (action.action_id, action.expected_state) for action in actions
        }
        issues: list[ConflictIssue] = []
        for action in actions:
            for condition in action.preconditions:
                device_id = condition.get("device_id")
                required = condition.get("state", {})
                produced_entry = final_states.get(device_id)
                if isinstance(required, Mapping) and produced_entry is not None:
                    producer_id, produced = produced_entry
                    if producer_id == action.action_id:
                        continue
                    conflicts = [
                        key
                        for key in set(required) & set(produced)
                        if required[key] != produced[key]
                    ]
                    if conflicts:
                        issues.append(
                            ConflictIssue(
                                "blocked_action",
                                "another action invalidates this action's precondition",
                                (action.action_id,),
                                {"blocking_device": device_id, "fields": sorted(conflicts)},
                            )
                        )
        return issues

    @staticmethod
    def _dependency_cycle(
        actions: Sequence[ActionProposal], dependencies: Mapping[str, Sequence[str]]
    ) -> list[str]:
        action_ids = {action.action_id for action in actions}
        visiting: set[str] = set()
        visited: set[str] = set()
        path: list[str] = []

        def visit(action_id: str) -> list[str]:
            if action_id in visiting:
                start = path.index(action_id)
                return path[start:] + [action_id]
            if action_id in visited:
                return []
            visiting.add(action_id)
            path.append(action_id)
            for dependency in dependencies.get(action_id, ()):
                if dependency in action_ids:
                    cycle = visit(dependency)
                    if cycle:
                        return cycle
            path.pop()
            visiting.remove(action_id)
            visited.add(action_id)
            return []

        for action_id in action_ids:
            cycle = visit(action_id)
            if cycle:
                return cycle
        return []
