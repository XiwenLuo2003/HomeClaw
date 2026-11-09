from __future__ import annotations

import json
import unittest
from pathlib import Path

from homeclaw.agent import LLMProposer, MCPActionDispatcher, ProductionRuntime, StaticProposer
from homeclaw.config import LLMConfig
from homeclaw.domain import (
    ActionProposal,
    CorrelationIds,
    DeviceRef,
    GroundingCandidate,
    GroundingResult,
    TaskStatus,
)
from homeclaw.llm import LLMResponse
from homeclaw.mcp_runtime import (
    DomainMCPServer,
    InProcessMCPClient,
    MCPHostGateway,
    MCPTool,
    MqttToolBinding,
    register_mqtt_tool,
)
from homeclaw.mqtt import CommandMapping, InMemoryMqttTransport, MqttCommandBridge
from homeclaw.observability import InMemoryTelemetry
from homeclaw.routing import RouteRequest, SkillRegistry, SkillRouter
from homeclaw.verification import (
    ActionVerifier,
    DeviceRecord,
    InMemoryCapabilityRegistry,
    ToolSpec,
)
from homeclaw.workflow import ExecutionBudget, InMemoryCheckpointStore
from homeclaw.security import AuthorizationPolicy, Principal, ToolAuthorizationRule


REGISTRY_PATH = Path(__file__).resolve().parents[1] / "homeclaw" / "skills" / "registry.json"


class JsonLLM:
    def __init__(self, payload):
        self.payload = payload
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return LLMResponse(
            text=json.dumps(self.payload),
            usage={"prompt_tokens": 100, "completion_tokens": 30},
        )


class ProductionRuntimeTests(unittest.TestCase):
    def components(self, *, respond=True, grounder=None):
        telemetry = InMemoryTelemetry()
        skill_registry = SkillRegistry.from_json(REGISTRY_PATH)
        router = SkillRouter(skill_registry, telemetry=telemetry)
        device = DeviceRef("home-1", "light-1", "living-room", "power")
        proposal = ActionProposal(
            "turn_light_on",
            device,
            {},
            "lighting",
            {"power": "on"},
            verification={"path": "power", "equals": "on"},
        )
        capability_registry = InMemoryCapabilityRegistry(
            [DeviceRecord(device, {"turn_light_on": ToolSpec("turn_light_on", "power")})]
        )
        verifier = ActionVerifier(capability_registry, telemetry=telemetry)

        transport = InMemoryMqttTransport()
        if respond:
            transport.on_publish = lambda topic, payload, broker: broker.inject(
                "home/home-1/light-1/state",
                {
                    "command_id": payload["command_id"],
                    "sequence": 4,
                    "state": {"power": "on"},
                },
            )
        bridge = MqttCommandBridge(
            transport,
            [CommandMapping("turn_light_on", "home/home-1/light-1/command", "home/home-1/light-1/state")],
            telemetry=telemetry,
        )
        server = DomainMCPServer()
        tool = skill_registry.get_tool("turn_light_on")
        register_mqtt_tool(
            server,
            bridge,
            MqttToolBinding(
                "turn_light_on",
                tool.description,
                tool.input_schema,
                "lighting",
                lambda arguments: {"power": "on"},
                timeout_seconds=0.001,
            ),
            home_id="home-1",
        )
        gateway = MCPHostGateway(InProcessMCPClient(server), telemetry)
        runtime = ProductionRuntime(
            store=InMemoryCheckpointStore(),
            router=router,
            proposer=StaticProposer([proposal]),
            verifier=verifier,
            dispatcher=MCPActionDispatcher(gateway),
            budget=ExecutionBudget(max_steps=20, max_replans=1),
            telemetry=telemetry,
            grounder=grounder,
        )
        return runtime, telemetry, transport

    def test_full_workflow_reaches_success_only_after_state_evidence(self) -> None:
        runtime, telemetry, transport = self.components(respond=True)

        result = runtime.execute("Turn on the living room light")

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertEqual(result.current_node.value, "complete")
        self.assertEqual(result.data["execution_evidence"][0]["status"], "succeeded")
        self.assertEqual(len(transport.published), 1)
        names = {span.name for span in telemetry.spans}
        self.assertTrue(
            {
                "agent.request",
                "router.retrieve",
                "planner.generate" if False else "workflow.plan",
                "verifier.check",
                "mcp.call",
                "mqtt.publish",
                "mqtt.wait_state",
            }.issubset(names)
        )
        trace_ids = {span.ids.trace_id for span in telemetry.spans}
        self.assertEqual(trace_ids, {result.ids.trace_id})

    def test_puback_without_state_never_becomes_false_done(self) -> None:
        runtime, telemetry, transport = self.components(respond=False)

        result = runtime.execute("Turn on the living room light")

        self.assertNotEqual(result.status, TaskStatus.SUCCEEDED)
        statuses = [item["status"] for item in result.data["execution_evidence"]]
        self.assertEqual(statuses, ["unknown"])
        self.assertGreaterEqual(len(transport.published), 1)

    def test_online_llm_proposer_sees_only_routed_tool_subset(self) -> None:
        registry = SkillRegistry.from_json(REGISTRY_PATH)
        router = SkillRouter(registry)
        route = router.route(RouteRequest("turn on the light", top_k=1))
        llm = JsonLLM(
            {
                "actions": [
                    {
                        "tool_name": "turn_light_on",
                        "home_id": "home-1",
                        "device_id": "light-1",
                        "room_id": "living-room",
                        "arguments": {},
                        "expected_state": {"power": "on"},
                        "verification": {"path": "power", "equals": "on"},
                        "source_skill": "lighting",
                        "idempotency": "idempotent_with_key",
                        "risk": "low"
                    }
                ]
            }
        )
        proposer_telemetry = InMemoryTelemetry()
        proposer = LLMProposer(llm, registry, telemetry=proposer_telemetry)

        result = proposer.propose("turn on the light", route, self._ids())

        self.assertEqual(result.total_tokens, 130)
        self.assertEqual(result.proposals[0].tool_name, "turn_light_on")
        serialized_prompt = llm.messages[1]["content"]
        self.assertIn("turn_light_on", serialized_prompt)
        self.assertNotIn("set_temperature", serialized_prompt)
        planner_span = proposer_telemetry.spans[0]
        self.assertEqual(planner_span.attributes["planner.prompt_tokens"], 100)
        self.assertEqual(planner_span.attributes["planner.completion_tokens"], 30)

    def test_visual_reference_runs_ground_node_before_planning(self) -> None:
        class Grounder:
            def __init__(self):
                self.calls = 0

            def resolve(self, **kwargs):
                self.calls += 1
                device = DeviceRef("home-1", "light-1", "living-room", "power")
                return GroundingResult(
                    query=kwargs["query"],
                    candidates=(GroundingCandidate(device, 0.95, evidence="visual match"),),
                    selected_device_id="light-1",
                    ambiguous=False,
                    model_version="test-grounder",
                )

        grounder = Grounder()
        runtime, _, _ = self.components(grounder=grounder)

        result = runtime.execute(
            "turn on that lamp in the image",
            context={
                "home_id": "home-1",
                "image_uri": "data:image/png;base64,AAAA",
                "room_id": "living-room",
                "capability": "power",
            },
        )

        self.assertEqual(result.status, TaskStatus.SUCCEEDED)
        self.assertIn("ground", result.completed_nodes)
        self.assertEqual(grounder.calls, 1)
        self.assertEqual(
            result.data["context"]["candidate_devices"][0]["device_id"], "light-1"
        )
        self.assertNotIn("ground_visual_device", result.data["route"]["tools"])

    def test_ambiguous_visual_grounding_rejects_before_device_execution(self) -> None:
        class AmbiguousGrounder:
            def resolve(self, **kwargs):
                devices = (
                    GroundingCandidate(DeviceRef("home-1", "light-1"), 0.51),
                    GroundingCandidate(DeviceRef("home-1", "light-2"), 0.49),
                )
                return GroundingResult(
                    query=kwargs["query"],
                    candidates=devices,
                    selected_device_id=None,
                    ambiguous=True,
                    model_version="test-grounder",
                )

        runtime, _, transport = self.components(grounder=AmbiguousGrounder())

        result = runtime.execute(
            "turn on that lamp in the image",
            context={"home_id": "home-1", "image_uri": "data:image/png;base64,AAAA"},
        )

        self.assertEqual(result.status, TaskStatus.REJECTED)
        self.assertEqual(result.data["reason"], "visual device reference remains ambiguous")
        self.assertEqual(transport.published, [])

    def test_dispatcher_passes_home_scope_to_versioned_authorization(self) -> None:
        server = DomainMCPServer()
        captured = {}
        server.register_tool(
            MCPTool(
                "set_light",
                "Set light",
                {"type": "object"},
                lambda arguments, ids: captured.update(arguments)
                or {
                    "status": "succeeded",
                    "source": "test",
                    "observed_state": {"power": "on"},
                },
            )
        )
        policy = AuthorizationPolicy(
            version="v1",
            rules={
                "set_light": ToolAuthorizationRule(
                    required_roles=frozenset({"device.operator"})
                )
            },
        )
        dispatcher = MCPActionDispatcher(
            MCPHostGateway(InProcessMCPClient(server), authorization=policy),
            principal=Principal(
                "user-1",
                frozenset({"device.operator"}),
                frozenset({"home-1"}),
            ),
            policy_version="v1",
        )
        proposal = ActionProposal(
            "set_light",
            DeviceRef("home-1", "light-1"),
            {"power": "on"},
            "lighting",
            {"power": "on"},
        )

        evidence = dispatcher.execute(
            proposal, CorrelationIds().for_command(), ["set_light"]
        )

        self.assertEqual(evidence.status.value, "succeeded")
        self.assertEqual(captured["home_id"], "home-1")

        cross_home = ActionProposal(
            "set_light",
            DeviceRef("home-2", "light-1"),
            {"power": "on"},
            "lighting",
            {"power": "on"},
        )
        with self.assertRaises(PermissionError):
            dispatcher.execute(
                cross_home, CorrelationIds().for_command(), ["set_light"]
            )

    @staticmethod
    def _ids():
        from homeclaw.domain import CorrelationIds

        return CorrelationIds()


if __name__ == "__main__":
    unittest.main()
