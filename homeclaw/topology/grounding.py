"""Knowledge-anchor filtering before visual grounding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from homeclaw.topology.graph import InMemoryTopologyStore, TopologyNode


@dataclass(frozen=True)
class CandidateAnchor:
    device_id: str
    name: str
    room_id: Optional[str]
    capabilities: tuple[str, ...]
    aliases: tuple[str, ...]


class TopologyCandidateFilter:
    def __init__(self, topology: InMemoryTopologyStore) -> None:
        self.topology = topology

    def candidates(
        self,
        *,
        room_id: Optional[str] = None,
        capability: Optional[str] = None,
        text_hint: str = "",
    ) -> tuple[CandidateAnchor, ...]:
        hint = text_hint.lower()
        matches: list[CandidateAnchor] = []
        for node in self.topology.nodes(kind="device"):
            properties = node.properties
            node_room = properties.get("room_id")
            capabilities = tuple(str(item) for item in properties.get("capabilities", ()))
            aliases = tuple(str(item) for item in properties.get("aliases", ()))
            if room_id is not None and node_room != room_id:
                continue
            if capability is not None and capability not in capabilities:
                continue
            names = (node.name, *aliases)
            if hint and not any(name.lower() in hint or hint in name.lower() for name in names):
                continue
            matches.append(
                CandidateAnchor(
                    device_id=node.node_id,
                    name=node.name,
                    room_id=str(node_room) if node_room is not None else None,
                    capabilities=capabilities,
                    aliases=aliases,
                )
            )
        return tuple(sorted(matches, key=lambda item: item.device_id))
