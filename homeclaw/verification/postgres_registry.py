"""PostgreSQL capability registry with optimistic updates and transactional outbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping, Optional

from homeclaw.domain import DeviceRef, IdempotencyClass, RiskLevel
from homeclaw.domain.models import new_id, utc_now
from homeclaw.verification.registry import DeviceRecord, ParameterSpec, ToolSpec


class RegistryConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class RegistryOutboxEvent:
    message_id: str
    home_id: str
    topic: str
    payload: Mapping[str, Any]
    created_at: datetime


def _parameter_schema(tool: ToolSpec) -> dict[str, Any]:
    return {
        name: {
            "kind": item.kind,
            "required": item.required,
            "minimum": item.minimum,
            "maximum": item.maximum,
            "choices": list(item.choices),
        }
        for name, item in tool.parameters.items()
    }


def _decode_schema(raw: Any) -> Mapping[str, Any]:
    return json.loads(raw) if isinstance(raw, str) else (raw or {})


class PostgresCapabilityRegistry:
    """A DB-API adapter; psycopg is only required by deployment composition."""

    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self.connection_factory = connection_factory

    @property
    def version(self) -> str:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(version), 0)::text FROM home_registry")
            row = cursor.fetchone()
        return str(row[0]) if row else "0"

    def create_home(
        self,
        home_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        message_id: str | None = None,
    ) -> int:
        payload = {"home_id": home_id, "version": 1, "metadata": dict(metadata or {})}
        try:
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO home_registry(home_id, metadata) VALUES (%s, %s::jsonb)",
                    (home_id, json.dumps(payload["metadata"], separators=(",", ":"))),
                )
                self._enqueue(cursor, home_id, "registry.home.created", payload, message_id)
        except Exception as exc:
            if getattr(exc, "sqlstate", None) == "23505":
                raise RegistryConflict(f"home already exists: {home_id}") from exc
            raise
        return 1

    def upsert_device(
        self,
        record: DeviceRecord,
        *,
        name: str,
        expected_home_version: int,
        metadata: Mapping[str, Any] | None = None,
        message_id: str | None = None,
    ) -> int:
        home_id = record.device.home_id
        device_id = record.device.device_id
        with self.connection_factory() as connection, connection.cursor() as cursor:
            version = self._advance_home(cursor, home_id, expected_home_version)
            cursor.execute(
                """
                INSERT INTO device_registry(
                  home_id, device_id, room_id, name, online, version,
                  state_version, state_observed_at, metadata
                ) VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s::jsonb)
                ON CONFLICT (home_id, device_id) DO UPDATE SET
                  room_id=EXCLUDED.room_id, name=EXCLUDED.name, online=EXCLUDED.online,
                  version=device_registry.version + 1,
                  state_version=EXCLUDED.state_version,
                  state_observed_at=EXCLUDED.state_observed_at,
                  metadata=EXCLUDED.metadata
                """,
                (
                    home_id,
                    device_id,
                    record.device.room_id,
                    name,
                    record.online,
                    record.state_version,
                    record.state_observed_at,
                    json.dumps(dict(metadata or {}), separators=(",", ":")),
                ),
            )
            # A device update is a complete capability snapshot.  Delete+insert
            # occurs in this same transaction after the home-version CAS.
            cursor.execute(
                "DELETE FROM capability_registry WHERE home_id=%s AND device_id=%s",
                (home_id, device_id),
            )
            for tool in record.tools.values():
                cursor.execute(
                    """
                    INSERT INTO capability_registry(
                      home_id, device_id, tool_name, capability, schema,
                      idempotency_class, risk, version
                    ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, 1)
                    """,
                    (
                        home_id,
                        device_id,
                        tool.name,
                        tool.capability,
                        json.dumps(_parameter_schema(tool), separators=(",", ":")),
                        tool.idempotency.value,
                        tool.risk.value,
                    ),
                )
            payload = {
                "home_id": home_id,
                "device_id": device_id,
                "home_version": version,
                "registry_version": record.registry_version,
                "tool_names": sorted(record.tools),
            }
            self._enqueue(cursor, home_id, "registry.device.changed", payload, message_id)
        return version

    def upsert_room(
        self,
        home_id: str,
        room_id: str,
        name: str,
        *,
        expected_home_version: int,
        metadata: Mapping[str, Any] | None = None,
        message_id: str | None = None,
    ) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            version = self._advance_home(cursor, home_id, expected_home_version)
            cursor.execute(
                """
                INSERT INTO room_registry(home_id, room_id, name, version, metadata)
                VALUES (%s, %s, %s, 1, %s::jsonb)
                ON CONFLICT (home_id, room_id) DO UPDATE SET
                  name=EXCLUDED.name, version=room_registry.version + 1,
                  metadata=EXCLUDED.metadata
                """,
                (
                    home_id,
                    room_id,
                    name,
                    json.dumps(dict(metadata or {}), separators=(",", ":")),
                ),
            )
            self._enqueue(
                cursor,
                home_id,
                "registry.room.changed",
                {"home_id": home_id, "room_id": room_id, "home_version": version},
                message_id,
            )
        return version

    def upsert_topology_edge(
        self,
        home_id: str,
        source_id: str,
        relation: str,
        target_id: str,
        *,
        expected_home_version: int,
        properties: Mapping[str, Any] | None = None,
        message_id: str | None = None,
    ) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            version = self._advance_home(cursor, home_id, expected_home_version)
            cursor.execute(
                """
                INSERT INTO topology_edge(
                  home_id, source_id, relation, target_id, properties, version
                ) VALUES (%s, %s, %s, %s, %s::jsonb, 1)
                ON CONFLICT (home_id, source_id, relation, target_id) DO UPDATE SET
                  properties=EXCLUDED.properties, version=topology_edge.version + 1
                """,
                (
                    home_id,
                    source_id,
                    relation,
                    target_id,
                    json.dumps(dict(properties or {}), separators=(",", ":")),
                ),
            )
            self._enqueue(
                cursor,
                home_id,
                "registry.topology.changed",
                {
                    "home_id": home_id,
                    "source_id": source_id,
                    "relation": relation,
                    "target_id": target_id,
                    "home_version": version,
                },
                message_id,
            )
        return version

    def get_device(self, home_id: str, device_id: str) -> Optional[DeviceRecord]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.room_id, d.online, d.version, d.state_version,
                       d.state_observed_at, c.tool_name, c.capability, c.schema,
                       c.idempotency_class, c.risk
                FROM device_registry d
                LEFT JOIN capability_registry c
                  ON c.home_id=d.home_id AND c.device_id=d.device_id
                WHERE d.home_id=%s AND d.device_id=%s
                ORDER BY c.tool_name
                """,
                (home_id, device_id),
            )
            rows = cursor.fetchall()
        if not rows:
            return None
        tools: dict[str, ToolSpec] = {}
        for row in rows:
            if row[5] is None:
                continue
            parameters = {
                name: ParameterSpec(
                    name,
                    raw["kind"],
                    bool(raw.get("required", True)),
                    raw.get("minimum"),
                    raw.get("maximum"),
                    tuple(raw.get("choices", ())),
                )
                for name, raw in _decode_schema(row[7]).items()
            }
            tools[row[5]] = ToolSpec(
                row[5],
                row[6],
                parameters,
                IdempotencyClass(row[8]),
                RiskLevel(row[9]),
            )
        first = rows[0]
        return DeviceRecord(
            DeviceRef(home_id, device_id, first[0]),
            tools,
            bool(first[1]),
            str(first[2]),
            first[3],
            first[4] or utc_now(),
        )

    def pending_events(self, limit: int = 100) -> tuple[RegistryOutboxEvent, ...]:
        if limit <= 0:
            raise ValueError("registry outbox limit must be positive")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT message_id, home_id, topic, payload, created_at
                FROM registry_outbox WHERE published_at IS NULL
                ORDER BY created_at LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return tuple(
            RegistryOutboxEvent(
                row[0],
                row[1],
                row[2],
                json.loads(row[3]) if isinstance(row[3], str) else row[3],
                row[4],
            )
            for row in rows
        )

    def mark_event_published(
        self, message_id: str, published_at: datetime | None = None
    ) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE registry_outbox SET published_at=%s
                WHERE message_id=%s AND published_at IS NULL RETURNING message_id
                """,
                (published_at or utc_now(), message_id),
            )
            if cursor.fetchone() is None:
                raise KeyError(message_id)

    @staticmethod
    def _advance_home(cursor: Any, home_id: str, expected_version: int) -> int:
        cursor.execute(
            """
            UPDATE home_registry SET version=version + 1, updated_at=NOW()
            WHERE home_id=%s AND version=%s RETURNING version
            """,
            (home_id, expected_version),
        )
        row = cursor.fetchone()
        if row is None:
            raise RegistryConflict(
                f"stale home registry writer: home={home_id}, expected={expected_version}"
            )
        return int(row[0])

    @staticmethod
    def _enqueue(
        cursor: Any,
        home_id: str,
        topic: str,
        payload: Mapping[str, Any],
        message_id: str | None,
    ) -> None:
        cursor.execute(
            """
            INSERT INTO registry_outbox(message_id, home_id, topic, payload)
            VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (message_id) DO NOTHING
            """,
            (
                message_id or new_id("msg"),
                home_id,
                topic,
                json.dumps(dict(payload), separators=(",", ":"), sort_keys=True),
            ),
        )
