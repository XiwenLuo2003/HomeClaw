from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from homeclaw.domain import (
    ActionStatus,
    CorrelationIds,
    ExecutionEvidence,
    MessageEnvelope,
)
from homeclaw.events import AioPikaEventBus, InMemoryEventBus
from homeclaw.mcp_runtime.sdk_adapter import AsyncMCPClientAdapter
from homeclaw.state import ApplyResult, VersionedStateDiff
from homeclaw.state.redis_adapter import RedisIdempotencyStore, RedisLease, RedisStateCache


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}

    def set(self, key, value, nx=False, px=None, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def eval(self, script, key_count, key, *args):
        if "HSET" in script:
            sequence, state_json, observed_at, expires_at, source, ttl, full_snapshot = args
            current = self.hashes.get(key, {}).get("sequence")
            if current is not None and int(current) >= int(sequence):
                return 0
            if current is not None and int(sequence) > int(current) + 1 and full_snapshot != "1":
                return -1
            self.hashes[key] = {
                "sequence": str(sequence),
                "state_json": state_json,
                "observed_at": observed_at,
                "expires_at": expires_at,
                "source": source,
            }
            return 1
        token = args[0]
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


class FakeSession:
    async def initialize(self):
        return "initialized"

    async def list_tools(self):
        return SimpleNamespace(
            tools=[SimpleNamespace(name="turn_light_on", description="Turn on", inputSchema={})]
        )

    async def call_tool(self, name, arguments):
        return {"name": name, "arguments": arguments}

    async def list_resources(self):
        return SimpleNamespace(
            resources=[SimpleNamespace(uri="home://state", name="state", description=None)]
        )

    async def read_resource(self, uri):
        return {"uri": uri}

    async def subscribe_resource(self, uri):
        return {"subscribed": uri}

    async def list_prompts(self):
        return SimpleNamespace(prompts=[SimpleNamespace(name="verify", description="Verify")])

    async def get_prompt(self, name, arguments):
        return {"name": name, "arguments": arguments}


class ProductionAdapterTests(unittest.TestCase):
    def test_event_bus_deduplicates_message_id(self) -> None:
        bus = InMemoryEventBus()
        received = []
        bus.subscribe("device.changed", received.append)
        envelope = MessageEnvelope(
            "device.changed",
            CorrelationIds(),
            {"device_id": "light-1"},
            "mqtt-bridge",
        )

        self.assertTrue(bus.publish(envelope))
        self.assertFalse(bus.publish(envelope))
        self.assertEqual(received, [envelope])

    def test_redis_state_cache_uses_sequence_cas(self) -> None:
        redis = FakeRedis()
        cache = RedisStateCache(redis, ttl_seconds=60)
        self.assertEqual(
            cache.apply(VersionedStateDiff("home-1", "light-1", 2, {"power": "on"})).value,
            "applied",
        )
        self.assertEqual(
            cache.apply(VersionedStateDiff("home-1", "light-1", 1, {"power": "off"})).value,
            "out_of_order",
        )
        self.assertEqual(cache.get("home-1", "light-1").state["power"], "on")

    def test_redis_state_cache_rejects_incremental_sequence_gap(self) -> None:
        redis = FakeRedis()
        cache = RedisStateCache(redis, ttl_seconds=60)
        cache.apply(VersionedStateDiff("home-1", "light-1", 1, {"power": "off"}))
        self.assertEqual(
            cache.apply(VersionedStateDiff("home-1", "light-1", 3, {"brightness": 40})),
            ApplyResult.GAP,
        )

    def test_redis_lease_releases_only_its_own_token(self) -> None:
        redis = FakeRedis()
        first = RedisLease(redis, "registry")
        second = RedisLease(redis, "registry")
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        self.assertFalse(second.release())
        self.assertTrue(first.release())

    def test_redis_idempotency_round_trips_execution_evidence(self) -> None:
        redis = FakeRedis()
        store = RedisIdempotencyStore(redis)
        ids = CorrelationIds().for_command("cmd-redis")
        evidence = ExecutionEvidence(
            ids,
            "action-1",
            ActionStatus.SUCCEEDED,
            "mqtt-state",
            {"power": "on"},
            "7",
        )

        self.assertTrue(store.claim("cmd-redis"))
        self.assertFalse(store.claim("cmd-redis"))
        store.put("cmd-redis", evidence)
        restored = store.get("cmd-redis")

        self.assertEqual(restored.status, ActionStatus.SUCCEEDED)
        self.assertEqual(restored.ids.command_id, "cmd-redis")
        self.assertEqual(restored.observed_state, {"power": "on"})

    def test_async_mcp_adapter_maps_official_session_shapes(self) -> None:
        async def scenario():
            client = AsyncMCPClientAdapter(FakeSession())
            self.assertEqual(await client.initialize(), "initialized")
            self.assertEqual((await client.list_tools())[0]["name"], "turn_light_on")
            self.assertEqual((await client.list_resources())[0]["uri"], "home://state")
            self.assertEqual((await client.list_prompts())[0]["name"], "verify")
            self.assertEqual(
                await client.call_tool("turn_light_on", {"device_id": "light-1"}),
                {"name": "turn_light_on", "arguments": {"device_id": "light-1"}},
            )

        asyncio.run(scenario())

    def test_rabbitmq_envelope_decoder_rejects_unknown_schema_version(self) -> None:
        envelope = MessageEnvelope(
            "device.changed",
            CorrelationIds(),
            {"device_id": "light-1"},
            "mqtt-bridge",
        )
        restored = AioPikaEventBus.decode_envelope(envelope.to_dict())
        self.assertEqual(restored.message_id, envelope.message_id)
        self.assertEqual(restored.created_at, envelope.created_at)

        incompatible = envelope.to_dict()
        incompatible["schema_version"] = "999"
        with self.assertRaises(ValueError):
            AioPikaEventBus.decode_envelope(incompatible)

    def test_async_mcp_adapter_enforces_timeout(self) -> None:
        class SlowSession:
            async def initialize(self):
                await asyncio.sleep(0.05)

        async def scenario():
            client = AsyncMCPClientAdapter(SlowSession(), timeout_seconds=0.001)
            with self.assertRaises(asyncio.TimeoutError):
                await client.initialize()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
