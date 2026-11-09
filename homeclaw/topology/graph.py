"""Optimistically versioned topology graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Mapping, Optional


class TopologyConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class TopologyNode:
    node_id: str
    kind: str
    name: str
    properties: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopologyEdge:
    source_id: str
    relation: str
    target_id: str
    properties: Mapping[str, Any] = field(default_factory=dict)


class InMemoryTopologyStore:
    def __init__(self) -> None:
        self._nodes: dict[str, TopologyNode] = {}
        self._edges: dict[tuple[str, str, str], TopologyEdge] = {}
        self._version = 0
        self._lock = RLock()

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def get_node(self, node_id: str) -> Optional[TopologyNode]:
        with self._lock:
            return self._nodes.get(node_id)

    def nodes(self, *, kind: Optional[str] = None) -> tuple[TopologyNode, ...]:
        with self._lock:
            items = tuple(self._nodes.values())
        return tuple(node for node in items if kind is None or node.kind == kind)

    def neighbors(self, node_id: str, relation: Optional[str] = None) -> tuple[TopologyNode, ...]:
        with self._lock:
            target_ids = [
                edge.target_id
                for edge in self._edges.values()
                if edge.source_id == node_id and (relation is None or edge.relation == relation)
            ]
            return tuple(self._nodes[target_id] for target_id in target_ids if target_id in self._nodes)

    def apply(
        self,
        *,
        nodes: tuple[TopologyNode, ...] = (),
        edges: tuple[TopologyEdge, ...] = (),
        expected_version: int,
    ) -> int:
        with self._lock:
            if self._version != expected_version:
                raise TopologyConflict(
                    f"stale topology writer: expected {expected_version}, actual {self._version}"
                )
            prospective_nodes = dict(self._nodes)
            for node in nodes:
                prospective_nodes[node.node_id] = node
            for edge in edges:
                if edge.source_id not in prospective_nodes or edge.target_id not in prospective_nodes:
                    raise ValueError("topology edge endpoints must exist")
            self._nodes = prospective_nodes
            for edge in edges:
                self._edges[(edge.source_id, edge.relation, edge.target_id)] = edge
            self._version += 1
            return self._version
