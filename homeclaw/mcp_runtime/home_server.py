"""Bind verified domain tools to an MQTT bridge behind the MCP boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from homeclaw.domain import ActionProposal, CorrelationIds, DeviceRef
from homeclaw.mcp_runtime.server import DomainMCPServer, MCPTool
from homeclaw.mqtt import MqttCommandBridge


@dataclass(frozen=True)
class MqttToolBinding:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    source_skill: str
    expected_state_builder: Callable[[Mapping[str, Any]], Mapping[str, Any]]
    timeout_seconds: float = 5.0


def register_mqtt_tool(
    server: DomainMCPServer,
    bridge: MqttCommandBridge,
    binding: MqttToolBinding,
    *,
    home_id: str,
) -> None:
    def handler(arguments: Mapping[str, Any], ids: CorrelationIds) -> Mapping[str, Any]:
        public_arguments = {
            key: value for key, value in arguments.items() if not key.startswith("_homeclaw_")
        }
        requested_home_id = str(public_arguments.pop("home_id", home_id))
        if requested_home_id != home_id:
            raise PermissionError(
                f"MCP tool is bound to {home_id}, not {requested_home_id}"
            )
        device_id = str(public_arguments.pop("device_id"))
        proposal = ActionProposal(
            tool_name=binding.name,
            target=DeviceRef(home_id, device_id),
            arguments=public_arguments,
            source_skill=binding.source_skill,
            expected_state=dict(binding.expected_state_builder(public_arguments)),
            verification={"source": "capability-registry"},
            action_id=str(arguments.get("_homeclaw_action_id") or "mcp-action"),
        )
        evidence = bridge.execute(proposal, ids, timeout_seconds=binding.timeout_seconds)
        return evidence.to_dict()

    server.register_tool(
        MCPTool(
            name=binding.name,
            description=binding.description,
            input_schema=binding.input_schema,
            handler=handler,
        )
    )
