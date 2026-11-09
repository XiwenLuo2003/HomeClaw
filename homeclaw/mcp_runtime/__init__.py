"""MCP domain facade independent of a concrete SDK transport."""

from homeclaw.mcp_runtime.host import MCPHostGateway
from homeclaw.mcp_runtime.server import (
    DomainMCPServer,
    InProcessMCPClient,
    MCPPrompt,
    MCPResource,
    MCPTool,
)
from homeclaw.mcp_runtime.home_server import MqttToolBinding, register_mqtt_tool
from homeclaw.mcp_runtime.sdk_adapter import AsyncMCPClientAdapter

__all__ = [
    "DomainMCPServer",
    "AsyncMCPClientAdapter",
    "InProcessMCPClient",
    "MCPHostGateway",
    "MCPPrompt",
    "MCPResource",
    "MCPTool",
    "MqttToolBinding",
    "register_mqtt_tool",
]
