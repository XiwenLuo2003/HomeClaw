"""Testable MCP semantics: tools, resources, prompts, and subscriptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, Mapping, Optional, Protocol

from homeclaw.domain import CorrelationIds


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: Callable[[Mapping[str, Any], CorrelationIds], Mapping[str, Any]] = field(
        repr=False, compare=False
    )
    version: str = "1"


@dataclass(frozen=True)
class MCPResource:
    uri: str
    name: str
    description: str
    reader: Callable[[], Mapping[str, Any]] = field(repr=False, compare=False)
    version: str = "1"


@dataclass(frozen=True)
class MCPPrompt:
    name: str
    description: str
    renderer: Callable[[Mapping[str, Any]], str] = field(repr=False, compare=False)
    version: str = "1"


class DomainMCPServer:
    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
        self._subscribers: dict[str, list[Callable[[str], None]]] = {}
        self._lock = RLock()

    def register_tool(self, tool: MCPTool) -> None:
        if "/" in tool.name or tool.name.startswith("mqtt"):
            raise ValueError("MCP tools must use domain names, not raw MQTT topics")
        if not tool.version.strip():
            raise ValueError("MCP tool version is required")
        with self._lock:
            if tool.name in self._tools:
                raise ValueError(f"duplicate MCP tool: {tool.name}")
            self._tools[tool.name] = tool

    def register_resource(self, resource: MCPResource) -> None:
        if not resource.version.strip():
            raise ValueError("MCP resource version is required")
        with self._lock:
            if resource.uri in self._resources:
                raise ValueError(f"duplicate MCP resource: {resource.uri}")
            self._resources[resource.uri] = resource

    def register_prompt(self, prompt: MCPPrompt) -> None:
        if not prompt.version.strip():
            raise ValueError("MCP prompt version is required")
        with self._lock:
            if prompt.name in self._prompts:
                raise ValueError(f"duplicate MCP prompt: {prompt.name}")
            self._prompts[prompt.name] = prompt

    def list_tools(self) -> list[dict[str, Any]]:
        with self._lock:
            tools = list(self._tools.values())
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": dict(tool.input_schema),
                "version": tool.version,
            }
            for tool in tools
        ]

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        ids: CorrelationIds,
    ) -> Mapping[str, Any]:
        with self._lock:
            tool = self._tools.get(name)
        if tool is None:
            raise KeyError(name)
        return tool.handler(arguments, ids)

    def list_resources(self) -> list[dict[str, str]]:
        with self._lock:
            resources = list(self._resources.values())
        return [
            {
                "uri": item.uri,
                "name": item.name,
                "description": item.description,
                "version": item.version,
            }
            for item in resources
        ]

    def read_resource(self, uri: str) -> Mapping[str, Any]:
        with self._lock:
            resource = self._resources.get(uri)
        if resource is None:
            raise KeyError(uri)
        return resource.reader()

    def subscribe_resource(self, uri: str, callback: Callable[[str], None]) -> None:
        with self._lock:
            if uri not in self._resources:
                raise KeyError(uri)
            self._subscribers.setdefault(uri, []).append(callback)

    def notify_resource_updated(self, uri: str) -> None:
        with self._lock:
            subscribers = list(self._subscribers.get(uri, ()))
        for callback in subscribers:
            callback(uri)

    def list_prompts(self) -> list[dict[str, str]]:
        with self._lock:
            prompts = list(self._prompts.values())
        return [
            {"name": item.name, "description": item.description, "version": item.version}
            for item in prompts
        ]

    def get_prompt(self, name: str, arguments: Mapping[str, Any]) -> str:
        with self._lock:
            prompt = self._prompts.get(name)
        if prompt is None:
            raise KeyError(name)
        return prompt.renderer(arguments)


class MCPClient(Protocol):
    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(
        self, name: str, arguments: Mapping[str, Any], ids: CorrelationIds
    ) -> Mapping[str, Any]:
        ...

    def read_resource(self, uri: str) -> Mapping[str, Any]:
        ...


class InProcessMCPClient:
    """MCP client used in tests and modular-monolith deployment."""

    def __init__(self, server: DomainMCPServer) -> None:
        self.server = server

    def list_tools(self) -> list[dict[str, Any]]:
        return self.server.list_tools()

    def call_tool(
        self, name: str, arguments: Mapping[str, Any], ids: CorrelationIds
    ) -> Mapping[str, Any]:
        return self.server.call_tool(name, arguments, ids)

    def read_resource(self, uri: str) -> Mapping[str, Any]:
        return self.server.read_resource(uri)
