"""Qwen3-VL Grounder inference client; no training dependencies are used."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, Sequence

from homeclaw.domain import BBox, DeviceRef, GroundingCandidate, GroundingResult


@dataclass(frozen=True)
class GrounderCandidate:
    device: DeviceRef
    name: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrounderRequest:
    image_uri: str
    query: str
    candidates: Sequence[GrounderCandidate]
    top_k: int = 5

    def __post_init__(self) -> None:
        if not self.image_uri.strip() or not self.query.strip():
            raise ValueError("grounder image_uri and query are required")
        if not self.candidates:
            raise ValueError("grounder requires topology-anchored candidates")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")


class GrounderClient(Protocol):
    def ground(self, request: GrounderRequest, timeout_seconds: float = 10.0) -> GroundingResult:
        ...

    def healthy(self, timeout_seconds: float = 2.0) -> bool:
        ...

    def ground_batch(
        self,
        requests: Sequence[GrounderRequest],
        timeout_seconds: float = 30.0,
    ) -> tuple[GroundingResult, ...]:
        ...


class HttpGrounderClient:
    """Standard-library HTTP client for the Dockerized GPU service."""

    def __init__(
        self,
        base_url: str,
        *,
        opener: Callable[..., Any] = urllib.request.urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._opener = opener

    def ground(self, request: GrounderRequest, timeout_seconds: float = 10.0) -> GroundingResult:
        payload = self._request_payload(request)
        http_request = urllib.request.Request(
            f"{self.base_url}/v1/ground",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._open_json(http_request, timeout_seconds)
        return self._parse_response(raw, request)

    def ground_batch(
        self,
        requests: Sequence[GrounderRequest],
        timeout_seconds: float = 30.0,
    ) -> tuple[GroundingResult, ...]:
        if not requests or len(requests) > 16:
            raise ValueError("grounder batch size must be in [1, 16]")
        payload = {"requests": [self._request_payload(item) for item in requests]}
        http_request = urllib.request.Request(
            f"{self.base_url}/v1/ground:batch",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        raw = self._open_json(http_request, timeout_seconds)
        results = raw.get("results", ())
        if len(results) != len(requests):
            raise ValueError("grounder batch response count mismatch")
        batch_latency = float(raw.get("latency_ms", 0.0))
        parsed = []
        for item, request in zip(results, requests):
            normalized = dict(item)
            normalized.setdefault("latency_ms", batch_latency / len(requests))
            parsed.append(self._parse_response(normalized, request))
        return tuple(parsed)

    def _open_json(self, request: urllib.request.Request, timeout_seconds: float) -> Any:
        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404, 409, 422):
                raise ValueError(f"grounder rejected request with HTTP {exc.code}") from exc
            raise ConnectionError(f"grounder HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise ConnectionError(f"grounder unavailable: {exc.reason}") from exc

    @staticmethod
    def _request_payload(request: GrounderRequest) -> dict[str, Any]:
        return {
            "image_uri": request.image_uri,
            "query": request.query,
            "top_k": request.top_k,
            "candidates": [
                {
                    "home_id": item.device.home_id,
                    "device_id": item.device.device_id,
                    "room_id": item.device.room_id,
                    "capability": item.device.capability,
                    "name": item.name,
                    "aliases": list(item.aliases),
                }
                for item in request.candidates
            ],
        }

    def healthy(self, timeout_seconds: float = 2.0) -> bool:
        request = urllib.request.Request(f"{self.base_url}/health", method="GET")
        try:
            with self._opener(request, timeout=timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return response.status == 200 and payload.get("status") in ("ready", "loading")
        except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError):
            return False

    @staticmethod
    def _parse_response(raw: Mapping[str, Any], request: GrounderRequest) -> GroundingResult:
        devices = {item.device.device_id: item.device for item in request.candidates}
        candidates: list[GroundingCandidate] = []
        for item in raw.get("candidates", []):
            device_id = str(item["device_id"])
            if device_id not in devices:
                raise ValueError(f"grounder returned device outside anchored candidates: {device_id}")
            bbox_raw = item.get("bbox")
            bbox = BBox(*map(float, bbox_raw)) if bbox_raw is not None else None
            candidates.append(
                GroundingCandidate(
                    device=devices[device_id],
                    score=float(item["score"]),
                    bbox=bbox,
                    evidence=str(item.get("evidence", "")),
                )
            )
        selected = raw.get("selected_device_id")
        return GroundingResult(
            query=request.query,
            candidates=tuple(candidates),
            selected_device_id=str(selected) if selected is not None else None,
            ambiguous=bool(raw.get("ambiguous", selected is None)),
            model_version=str(raw.get("model_version", "unknown")),
            latency_ms=float(raw.get("latency_ms", 0.0)),
        )
