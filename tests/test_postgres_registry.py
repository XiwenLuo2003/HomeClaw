from __future__ import annotations

import unittest

from homeclaw.domain import DeviceRef
from homeclaw.verification import (
    DeviceRecord,
    PostgresCapabilityRegistry,
    RegistryConflict,
    ToolSpec,
)


class FakeCursor:
    def __init__(self, advance_result=(2,)) -> None:
        self.advance_result = advance_result
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, parameters=()):
        self.statements.append((" ".join(sql.split()), parameters))

    def fetchone(self):
        result = self.advance_result
        self.advance_result = None
        return result


class FakeConnection:
    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


class PostgresRegistryTests(unittest.TestCase):
    def test_device_snapshot_and_outbox_share_one_transaction(self) -> None:
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        registry = PostgresCapabilityRegistry(lambda: connection)
        device = DeviceRef("home-1", "light-1", "living-room", "power")
        record = DeviceRecord(
            device,
            {"turn_light_on": ToolSpec("turn_light_on", "power")},
        )

        version = registry.upsert_device(
            record,
            name="Living-room light",
            expected_home_version=1,
            message_id="message-1",
        )

        self.assertEqual(version, 2)
        rendered = "\n".join(sql for sql, _ in cursor.statements)
        self.assertIn("UPDATE home_registry", rendered)
        self.assertIn("DELETE FROM capability_registry", rendered)
        self.assertIn("INSERT INTO capability_registry", rendered)
        self.assertIn("INSERT INTO registry_outbox", rendered)
        self.assertEqual(cursor.statements[-1][1][0], "message-1")

    def test_stale_home_version_aborts_before_device_mutation(self) -> None:
        cursor = FakeCursor(advance_result=None)
        registry = PostgresCapabilityRegistry(lambda: FakeConnection(cursor))
        record = DeviceRecord(
            DeviceRef("home-1", "light-1"),
            {"turn_light_on": ToolSpec("turn_light_on", "power")},
        )

        with self.assertRaises(RegistryConflict):
            registry.upsert_device(record, name="Light", expected_home_version=9)

        self.assertEqual(len(cursor.statements), 1)
        self.assertIn("UPDATE home_registry", cursor.statements[0][0])

    def test_room_and_topology_updates_each_use_version_cas_and_outbox(self) -> None:
        room_cursor = FakeCursor((2,))
        room_registry = PostgresCapabilityRegistry(
            lambda: FakeConnection(room_cursor)
        )
        self.assertEqual(
            room_registry.upsert_room(
                "home-1",
                "living-room",
                "Living room",
                expected_home_version=1,
                message_id="room-message",
            ),
            2,
        )
        room_sql = "\n".join(sql for sql, _ in room_cursor.statements)
        self.assertIn("INSERT INTO room_registry", room_sql)
        self.assertIn("INSERT INTO registry_outbox", room_sql)

        edge_cursor = FakeCursor((3,))
        edge_registry = PostgresCapabilityRegistry(
            lambda: FakeConnection(edge_cursor)
        )
        self.assertEqual(
            edge_registry.upsert_topology_edge(
                "home-1",
                "light-1",
                "located_in",
                "living-room",
                expected_home_version=2,
                message_id="edge-message",
            ),
            3,
        )
        edge_sql = "\n".join(sql for sql, _ in edge_cursor.statements)
        self.assertIn("INSERT INTO topology_edge", edge_sql)
        self.assertIn("registry.topology.changed", edge_cursor.statements[-1][1][2])


if __name__ == "__main__":
    unittest.main()
