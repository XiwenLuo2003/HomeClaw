"""MCP-facing domain command bridge that hides raw MQTT topics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Mapping, Optional, Protocol

from homeclaw.domain import (
    ActionProposal,
    ActionStatus,
    CorrelationIds,
    ErrorCode,
    ErrorDetail,
    ExecutionEvidence,
)
from homeclaw.mqtt.transport import MqttMessage, MqttTransport
from homeclaw.state import InMemoryStateCache, VersionedStateDiff, matches_expected_state
from homeclaw.observability import NoopTelemetry, Telemetry
from homeclaw.resilience import CircuitBreaker, CircuitOpen, RetryPolicy, retry_call


@dataclass(frozen=True)
class CommandMapping:
    tool_name: str
    command_topic: str
    state_topic: str
    qos: int = 1
    max_state_age_seconds: float = 60.0
    availability_topic: str | None = None
    availability_probe_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.command_topic or not self.state_topic:
            raise ValueError("command and state topics are required")
        if self.command_topic == self.state_topic:
            raise ValueError("command and state topics must be distinct")
        if self.max_state_age_seconds <= 0:
            raise ValueError("max_state_age_seconds must be positive")
        if self.availability_probe_seconds < 0:
            raise ValueError("availability_probe_seconds must be non-negative")


class IdempotencyStore(Protocol):
    def get(self, command_id: str) -> Optional[ExecutionEvidence]:
        ...

    def put(self, command_id: str, evidence: ExecutionEvidence) -> None:
        ...

    def claim(self, command_id: str) -> bool:
        ...


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._items: dict[str, ExecutionEvidence] = {}
        self._claimed: set[str] = set()
        self._lock = RLock()

    def get(self, command_id: str) -> Optional[ExecutionEvidence]:
        with self._lock:
            return self._items.get(command_id)

    def put(self, command_id: str, evidence: ExecutionEvidence) -> None:
        with self._lock:
            self._items[command_id] = evidence
            self._claimed.add(command_id)

    def claim(self, command_id: str) -> bool:
        with self._lock:
            if command_id in self._claimed:
                return False
            self._claimed.add(command_id)
            return True


class MqttCommandBridge:
    def __init__(
        self,
        transport: MqttTransport,
        mappings: list[CommandMapping],
        *,
        idempotency: IdempotencyStore | None = None,
        state_cache: InMemoryStateCache | None = None,
        telemetry: Telemetry | None = None,
        publish_retry_policy: RetryPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self.transport = transport
        self.mappings = {mapping.tool_name: mapping for mapping in mappings}
        self.idempotency = idempotency or InMemoryIdempotencyStore()
        self.state_cache = state_cache or InMemoryStateCache()
        self.telemetry = telemetry or NoopTelemetry()
        self.publish_retry_policy = publish_retry_policy or RetryPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def execute(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds,
        *,
        timeout_seconds: float = 5.0,
    ) -> ExecutionEvidence:
        ids = ids if ids.command_id is not None else ids.for_command()
        assert ids.command_id is not None
        cached = self.idempotency.get(ids.command_id)
        if cached is not None:
            if cached.status is ActionStatus.UNKNOWN:
                mapping = self.mappings.get(proposal.tool_name)
                if mapping is not None:
                    refreshed = self._wait_for_confirmation(
                        proposal, ids, mapping, timeout_seconds
                    )
                    if refreshed is not None:
                        self.idempotency.put(ids.command_id, refreshed)
                        return refreshed
            return cached
        if not self.idempotency.claim(ids.command_id):
            return self._error(
                ids,
                proposal.action_id,
                ActionStatus.UNKNOWN,
                ErrorCode.EXECUTION_UNCONFIRMED,
                "duplicate command is already in flight",
                retryable=True,
            )

        mapping = self.mappings.get(proposal.tool_name)
        if mapping is None:
            evidence = self._error(
                ids,
                proposal.action_id,
                ActionStatus.REJECTED,
                ErrorCode.CAPABILITY_NOT_FOUND,
                f"no MQTT mapping for {proposal.tool_name}",
                retryable=False,
            )
            self.idempotency.put(ids.command_id, evidence)
            return evidence

        if self._known_offline(mapping):
            evidence = self._error(
                ids,
                proposal.action_id,
                ActionStatus.FAILED,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                "device availability reports offline",
                retryable=True,
            )
            self.idempotency.put(ids.command_id, evidence)
            return evidence

        payload: dict[str, object] = {
            "command_id": ids.command_id,
            "action_id": proposal.action_id,
            "device_id": proposal.target.device_id,
            "arguments": dict(proposal.arguments),
        }
        self.transport.ensure_subscription(mapping.state_topic, qos=mapping.qos)
        def publish_once():
            with self.circuit_breaker.call():
                with self.telemetry.span(
                    "mqtt.publish",
                    ids,
                    {"mqtt.tool": proposal.tool_name, "mqtt.qos": mapping.qos},
                ):
                    current = self.transport.publish(
                        mapping.command_topic, payload, qos=mapping.qos
                    )
                    if not current.accepted:
                        raise ConnectionError(current.reason or "MQTT publish rejected")
                    return current

        try:
            receipt = retry_call(
                publish_once,
                policy=self.publish_retry_policy,
                idempotency=proposal.idempotency,
            )
        except CircuitOpen as exc:
            evidence = self._error(
                ids,
                proposal.action_id,
                ActionStatus.FAILED,
                ErrorCode.CIRCUIT_OPEN,
                str(exc),
                retryable=True,
            )
            self.idempotency.put(ids.command_id, evidence)
            return evidence
        except (ConnectionError, TimeoutError) as exc:
            evidence = self._error(
                ids,
                proposal.action_id,
                ActionStatus.FAILED,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                str(exc),
                retryable=True,
            )
            self.idempotency.put(ids.command_id, evidence)
            return evidence

        evidence = self._wait_for_confirmation(proposal, ids, mapping, timeout_seconds)
        if evidence is None:
            evidence = self._error(
                ids,
                proposal.action_id,
                ActionStatus.UNKNOWN,
                ErrorCode.EXECUTION_UNCONFIRMED,
                "MQTT publish was accepted but no matching device state was observed",
                retryable=True,
            )
            self.idempotency.put(ids.command_id, evidence)
            return evidence
        self.idempotency.put(ids.command_id, evidence)
        return evidence

    def _known_offline(self, mapping: CommandMapping) -> bool:
        if not mapping.availability_topic:
            return False
        self.transport.ensure_subscription(mapping.availability_topic, qos=mapping.qos)

        def availability(message: MqttMessage) -> bool:
            if message.retained:
                raw = message.payload.get("observed_at")
                if not isinstance(raw, str):
                    return False
                try:
                    observed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                except ValueError:
                    return False
                age_seconds = (
                    datetime.now(timezone.utc) - observed.astimezone(timezone.utc)
                ).total_seconds()
                if age_seconds > mapping.max_state_age_seconds:
                    return False
            return "online" in message.payload or "status" in message.payload

        message = self.transport.wait_for_message(
            mapping.availability_topic,
            availability,
            mapping.availability_probe_seconds,
        )
        if message is None:
            return False
        value = message.payload.get("online", message.payload.get("status"))
        if isinstance(value, bool):
            return not value
        return str(value).strip().lower() in {"offline", "false", "0", "unavailable"}

    def _wait_for_confirmation(
        self,
        proposal: ActionProposal,
        ids: CorrelationIds,
        mapping: CommandMapping,
        timeout_seconds: float,
    ) -> Optional[ExecutionEvidence]:
        assert ids.command_id is not None

        def terminal_for_command(message: MqttMessage) -> bool:
            payload_command_id = message.payload.get("command_id")
            if payload_command_id not in (None, ids.command_id):
                return False
            if (
                payload_command_id == ids.command_id
                and str(message.payload.get("status", "")).lower()
                in {"rejected", "failed"}
            ):
                return True
            if message.retained and payload_command_id != ids.command_id:
                return False
            observed_at_raw = message.payload.get("observed_at")
            if message.retained:
                if not isinstance(observed_at_raw, str):
                    return False
                try:
                    observed_at = datetime.fromisoformat(observed_at_raw.replace("Z", "+00:00"))
                except ValueError:
                    return False
                age = datetime.now(timezone.utc) - observed_at.astimezone(timezone.utc)
                if age.total_seconds() > mapping.max_state_age_seconds:
                    return False
            state = message.payload.get("state", message.payload)
            return isinstance(state, Mapping) and matches_expected_state(state, proposal.expected_state)

        with self.telemetry.span(
            "mqtt.wait_state",
            ids,
            {"mqtt.timeout_seconds": timeout_seconds},
        ) as span:
            state_message = self.transport.wait_for_message(
                mapping.state_topic,
                terminal_for_command,
                timeout_seconds,
            )
            span.attributes["mqtt.confirmed"] = state_message is not None
        if state_message is None:
            return None
        reported_status = str(state_message.payload.get("status", "")).lower()
        if reported_status in {"rejected", "failed"}:
            reason = str(state_message.payload.get("reason", "device rejected command"))
            return self._error(
                ids,
                proposal.action_id,
                ActionStatus.REJECTED,
                ErrorCode.EXECUTION_REJECTED,
                reason,
                retryable=False,
            )
        observed = state_message.payload.get("state", state_message.payload)
        assert isinstance(observed, Mapping)
        sequence = int(state_message.payload.get("sequence", 0))
        self.state_cache.apply(
            VersionedStateDiff(
                home_id=proposal.target.home_id,
                device_id=proposal.target.device_id,
                sequence=sequence,
                changes=dict(observed),
                observed_at=state_message.received_at,
                source="mqtt-state",
                full_snapshot=True,
            )
        )
        return ExecutionEvidence(
            ids=ids,
            action_id=proposal.action_id,
            status=ActionStatus.SUCCEEDED,
            source="mqtt-state",
            observed_state=dict(observed),
            state_version=str(sequence),
        )

    @staticmethod
    def _error(
        ids: CorrelationIds,
        action_id: str,
        status: ActionStatus,
        code: ErrorCode,
        message: str,
        retryable: bool,
    ) -> ExecutionEvidence:
        return ExecutionEvidence(
            ids=ids,
            action_id=action_id,
            status=status,
            source="mqtt-bridge",
            error=ErrorDetail(
                code=code,
                message=message,
                retryable=retryable,
                component="mqtt-bridge",
            ),
        )
