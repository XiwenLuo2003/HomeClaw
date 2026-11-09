"""Host-side allowlist and telemetry boundary for MCP calls."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from homeclaw.domain import CorrelationIds
from homeclaw.mcp_runtime.server import MCPClient
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.security import AuthorizationPolicy, Principal


class MCPHostGateway:
    def __init__(
        self,
        client: MCPClient,
        telemetry: Telemetry | None = None,
        authorization: AuthorizationPolicy | None = None,
    ) -> None:
        self.client = client
        self.telemetry = telemetry or NoopTelemetry()
        self.authorization = authorization

    def exposed_tools(self, allowed_tools: Sequence[str]) -> list[dict[str, Any]]:
        allowed = set(allowed_tools)
        return [tool for tool in self.client.list_tools() if tool["name"] in allowed]

    def call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        ids: CorrelationIds,
        *,
        allowed_tools: Sequence[str],
        principal: Principal | None = None,
        policy_version: str | None = None,
        confirmed: bool = False,
    ) -> Mapping[str, Any]:
        if tool_name not in set(allowed_tools):
            raise PermissionError(f"tool is not exposed by selected skills: {tool_name}")
        if self.authorization is not None:
            if principal is None:
                raise PermissionError("authenticated principal is required")
            self.authorization.authorize(
                principal=principal,
                tool_name=tool_name,
                arguments=arguments,
                expected_version=policy_version,
                confirmed=confirmed,
            )
        attributes = {
            "mcp.tool": tool_name,
            "authorization.policy_version": (
                self.authorization.version if self.authorization is not None else "disabled"
            ),
            "principal.authenticated": principal is not None and principal.authenticated,
            "principal.role_count": len(principal.roles) if principal is not None else 0,
        }
        with self.telemetry.span("mcp.call", ids, attributes):
            return self.client.call_tool(tool_name, arguments, ids)
