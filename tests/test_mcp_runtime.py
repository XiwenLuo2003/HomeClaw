from __future__ import annotations

import unittest

from homeclaw.domain import CorrelationIds
from homeclaw.mcp_runtime import (
    DomainMCPServer,
    InProcessMCPClient,
    MCPHostGateway,
    MCPPrompt,
    MCPResource,
    MCPTool,
)
from homeclaw.observability import InMemoryTelemetry
from homeclaw.security import AuthorizationPolicy, Principal, ToolAuthorizationRule


class MCPRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {"power": "off", "brightness": 0}
        self.server = DomainMCPServer()
        self.server.register_tool(
            MCPTool(
                name="set_light_brightness",
                description="Set a light to an absolute brightness",
                input_schema={
                    "type": "object",
                    "properties": {"brightness": {"type": "integer", "minimum": 0, "maximum": 100}},
                    "required": ["brightness"],
                },
                handler=self._set_brightness,
            )
        )
        self.server.register_resource(
            MCPResource(
                uri="home://home-1/devices/light-1/state",
                name="Living-room light state",
                description="Aggregated current device state",
                reader=lambda: dict(self.state),
            )
        )
        self.server.register_prompt(
            MCPPrompt(
                name="verify_device_action",
                description="Render a verifier instruction",
                renderer=lambda args: f"Verify {args['tool']} against registry evidence.",
            )
        )

    def _set_brightness(self, arguments, ids):
        self.state["brightness"] = arguments["brightness"]
        return {"status": "confirmed", "command_id": ids.command_id}

    def test_host_exposes_only_selected_skill_tools(self) -> None:
        telemetry = InMemoryTelemetry()
        gateway = MCPHostGateway(InProcessMCPClient(self.server), telemetry)
        ids = CorrelationIds().for_command()

        exposed = gateway.exposed_tools(["set_light_brightness"])
        result = gateway.call(
            "set_light_brightness",
            {"brightness": 40},
            ids,
            allowed_tools=["set_light_brightness"],
        )

        self.assertEqual([tool["name"] for tool in exposed], ["set_light_brightness"])
        self.assertEqual(exposed[0]["version"], "1")
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(telemetry.spans[0].name, "mcp.call")
        with self.assertRaises(PermissionError):
            gateway.call("set_light_brightness", {}, ids, allowed_tools=[])

    def test_resources_are_read_on_demand_and_notify_subscribers(self) -> None:
        notifications = []
        uri = "home://home-1/devices/light-1/state"
        self.server.subscribe_resource(uri, notifications.append)
        self.state["power"] = "on"
        self.server.notify_resource_updated(uri)

        self.assertEqual(self.server.read_resource(uri)["power"], "on")
        self.assertEqual(notifications, [uri])
        self.assertEqual(self.server.list_resources()[0]["version"], "1")

    def test_prompt_is_separate_from_mutable_resource_state(self) -> None:
        prompt = self.server.get_prompt("verify_device_action", {"tool": "turn_on"})
        self.assertEqual(prompt, "Verify turn_on against registry evidence.")
        self.assertEqual(self.server.list_prompts()[0]["version"], "1")

    def test_raw_mqtt_topic_cannot_be_registered_as_tool(self) -> None:
        with self.assertRaises(ValueError):
            self.server.register_tool(
                MCPTool("mqtt/home/light/set", "raw", {}, lambda args, ids: {})
            )

    def test_versioned_authorization_is_fail_closed_and_tenant_scoped(self) -> None:
        policy = AuthorizationPolicy(
            version="policy-v3",
            rules={
                "set_light_brightness": ToolAuthorizationRule(
                    required_roles=frozenset({"device.operator"}),
                    require_confirmation=True,
                )
            },
        )
        gateway = MCPHostGateway(InProcessMCPClient(self.server), authorization=policy)
        principal = Principal(
            subject="user-1",
            roles=frozenset({"device.operator"}),
            home_ids=frozenset({"home-1"}),
        )
        ids = CorrelationIds().for_command()

        result = gateway.call(
            "set_light_brightness",
            {"home_id": "home-1", "brightness": 25},
            ids,
            allowed_tools=["set_light_brightness"],
            principal=principal,
            policy_version="policy-v3",
            confirmed=True,
        )
        self.assertEqual(result["status"], "confirmed")

        denied_cases = (
            {"principal": None, "policy_version": "policy-v3", "confirmed": True},
            {"principal": principal, "policy_version": "policy-v2", "confirmed": True},
            {"principal": principal, "policy_version": "policy-v3", "confirmed": False},
        )
        for case in denied_cases:
            with self.subTest(case=case), self.assertRaises(PermissionError):
                gateway.call(
                    "set_light_brightness",
                    {"home_id": "home-1", "brightness": 25},
                    ids,
                    allowed_tools=["set_light_brightness"],
                    **case,
                )

        with self.assertRaises(PermissionError):
            gateway.call(
                "set_light_brightness",
                {"home_id": "home-2", "brightness": 25},
                ids,
                allowed_tools=["set_light_brightness"],
                principal=principal,
                policy_version="policy-v3",
                confirmed=True,
            )


if __name__ == "__main__":
    unittest.main()
