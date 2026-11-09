"""Validated Skill/Tool registry with shared-tool references."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from homeclaw.routing.models import SkillDefinition, ToolDefinition


class SkillRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self._skills: dict[str, SkillDefinition] = {}

    @property
    def tools(self) -> tuple[ToolDefinition, ...]:
        return tuple(self._tools.values())

    @property
    def skills(self) -> tuple[SkillDefinition, ...]:
        return tuple(self._skills.values())

    def register_tool(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool definition: {tool.name}")
        self._tools[tool.name] = tool

    def register_skill(self, skill: SkillDefinition) -> None:
        if skill.skill_id in self._skills:
            raise ValueError(f"duplicate skill definition: {skill.skill_id}")
        missing = sorted(set(skill.tool_names) - set(self._tools))
        if missing:
            raise ValueError(f"skill {skill.skill_id} references unknown tools: {missing}")
        self._skills[skill.skill_id] = skill

    def get_skill(self, skill_id: str) -> Optional[SkillDefinition]:
        return self._skills.get(skill_id)

    def get_tool(self, tool_name: str) -> Optional[ToolDefinition]:
        return self._tools.get(tool_name)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "SkillRegistry":
        registry = cls()
        for item in raw.get("tools", []):
            registry.register_tool(
                ToolDefinition(
                    name=item["name"],
                    description=item["description"],
                    input_schema=item.get("input_schema", {"type": "object"}),
                    risk=item.get("risk", "low"),
                )
            )
        for item in raw.get("skills", []):
            registry.register_skill(
                SkillDefinition(
                    skill_id=item["skill_id"],
                    domain=item["domain"],
                    description=item["description"],
                    keywords=tuple(item.get("keywords", ())),
                    tool_names=tuple(item["tool_names"]),
                    knowledge_resource_uris=tuple(item.get("knowledge_resource_uris", ())),
                    activation_phrases=tuple(item.get("activation_phrases", ())),
                    competence=float(item.get("competence", 0.5)),
                    available=bool(item.get("available", True)),
                    version=str(item.get("version", "1")),
                )
            )
        return registry

    @classmethod
    def from_json(cls, path: str | Path) -> "SkillRegistry":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
