"""Versioned capability-registry contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Optional, Protocol

from homeclaw.domain import DeviceRef, IdempotencyClass, RiskLevel
from homeclaw.domain.models import utc_now


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    kind: str
    required: bool = True
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: tuple[Any, ...] = ()

    def validate(self, value: Any) -> Optional[str]:
        kinds = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
        }
        expected = kinds.get(self.kind)
        if expected is None:
            return f"unsupported parameter kind: {self.kind}"
        if not isinstance(value, expected) or (self.kind in ("integer", "number") and isinstance(value, bool)):
            return f"parameter {self.name} must be {self.kind}"
        if self.minimum is not None and value < self.minimum:
            return f"parameter {self.name} must be >= {self.minimum}"
        if self.maximum is not None and value > self.maximum:
            return f"parameter {self.name} must be <= {self.maximum}"
        if self.choices and value not in self.choices:
            return f"parameter {self.name} must be one of {self.choices}"
        return None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    capability: str
    parameters: Mapping[str, ParameterSpec] = field(default_factory=dict)
    idempotency: IdempotencyClass = IdempotencyClass.IDEMPOTENT_WITH_KEY
    risk: RiskLevel = RiskLevel.LOW


@dataclass(frozen=True)
class DeviceRecord:
    device: DeviceRef
    tools: Mapping[str, ToolSpec]
    online: bool = True
    registry_version: str = "1"
    state_version: Optional[str] = None
    state_observed_at: datetime = field(default_factory=utc_now)


class CapabilityRegistry(Protocol):
    @property
    def version(self) -> str:
        ...

    def get_device(self, home_id: str, device_id: str) -> Optional[DeviceRecord]:
        ...


class InMemoryCapabilityRegistry:
    def __init__(self, devices: list[DeviceRecord] | None = None, version: str = "1") -> None:
        self._version = version
        self._devices: dict[tuple[str, str], DeviceRecord] = {}
        for device in devices or []:
            self.upsert(device)

    @property
    def version(self) -> str:
        return self._version

    def get_device(self, home_id: str, device_id: str) -> Optional[DeviceRecord]:
        return self._devices.get((home_id, device_id))

    def upsert(self, record: DeviceRecord) -> None:
        self._devices[(record.device.home_id, record.device.device_id)] = record
