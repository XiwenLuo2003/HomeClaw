"""Optional async adapter around the official MCP Python ClientSession."""

from __future__ import annotations

import asyncio
from typing import Any, Mapping, Sequence


class AsyncMCPClientAdapter:
    def __init__(self, session: Any, timeout_seconds: float = 30.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("MCP timeout must be positive")
        self.session = session
        self.timeout_seconds = timeout_seconds

    async def _call(self, awaitable: Any) -> Any:
        return await asyncio.wait_for(awaitable, timeout=self.timeout_seconds)

    async def initialize(self) -> Any:
        return await self._call(self.session.initialize())

    async def list_tools(self) -> list[dict[str, Any]]:
        response = await self._call(self.session.list_tools())
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
            }
            for tool in response.tools
        ]

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        return await self._call(self.session.call_tool(name, arguments=dict(arguments)))

    async def list_resources(self) -> list[dict[str, Any]]:
        response = await self._call(self.session.list_resources())
        return [
            {"uri": str(resource.uri), "name": resource.name, "description": resource.description or ""}
            for resource in response.resources
        ]

    async def read_resource(self, uri: str) -> Any:
        return await self._call(self.session.read_resource(uri))

    async def subscribe_resource(self, uri: str) -> Any:
        return await self._call(self.session.subscribe_resource(uri))

    async def list_prompts(self) -> list[dict[str, Any]]:
        response = await self._call(self.session.list_prompts())
        return [
            {"name": prompt.name, "description": prompt.description or ""}
            for prompt in response.prompts
        ]

    async def get_prompt(self, name: str, arguments: Mapping[str, str]) -> Any:
        return await self._call(self.session.get_prompt(name, arguments=dict(arguments)))
