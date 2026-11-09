"""Fail-closed authorization for domain-level tool calls.

Authentication itself belongs at the deployment boundary.  This module consumes
the already authenticated principal and keeps authorization deterministic and
independent from an LLM decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: frozenset[str] = field(default_factory=frozenset)
    home_ids: frozenset[str] = field(default_factory=frozenset)
    authenticated: bool = True


@dataclass(frozen=True)
class ToolAuthorizationRule:
    required_roles: frozenset[str] = field(default_factory=frozenset)
    require_confirmation: bool = False


class AuthorizationPolicy:
    """Versioned, fail-closed RBAC plus home-tenant isolation policy."""

    def __init__(
        self,
        *,
        version: str,
        rules: Mapping[str, ToolAuthorizationRule],
    ) -> None:
        if not version.strip():
            raise ValueError("authorization policy version must not be empty")
        self.version = version
        self._rules = dict(rules)

    def authorize(
        self,
        *,
        principal: Principal,
        tool_name: str,
        arguments: Mapping[str, Any],
        expected_version: str | None = None,
        confirmed: bool = False,
    ) -> None:
        if expected_version is not None and expected_version != self.version:
            raise PermissionError(
                f"stale authorization policy: expected {expected_version}, active {self.version}"
            )
        if not principal.authenticated or not principal.subject.strip():
            raise PermissionError("authenticated principal is required")

        rule = self._rules.get(tool_name)
        if rule is None:
            raise PermissionError(f"tool has no authorization rule: {tool_name}")
        if not rule.required_roles.issubset(principal.roles):
            raise PermissionError(f"principal lacks role for tool: {tool_name}")
        if rule.require_confirmation and not confirmed:
            raise PermissionError(f"explicit user confirmation is required: {tool_name}")

        home_id = arguments.get("home_id")
        if home_id is not None and str(home_id) not in principal.home_ids:
            raise PermissionError(f"principal cannot access home: {home_id}")
