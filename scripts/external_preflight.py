"""Read-only preflight for production acceptance dependencies.

This command never installs packages, starts containers, opens sockets, or
prints secret values.  It only records which optional modules, executables,
configuration names, and repository assets are available.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

MODULES = {
    "mcp": "MCP SDK integration",
    "paho.mqtt.client": "MQTT transport",
    "redis": "Redis cache/idempotency",
    "psycopg": "PostgreSQL checkpoint store",
    "pymongo": "MongoDB temporal memory",
    "aio_pika": "RabbitMQ event bus",
    "opentelemetry.sdk": "OpenTelemetry export",
}
CONFIG_NAMES = (
    "HOMECLAW_POSTGRES_DSN",
    "HOMECLAW_REDIS_URL",
    "HOMECLAW_MONGO_URL",
    "HOMECLAW_RABBITMQ_URL",
    "HOMECLAW_MQTT_HOST",
    "HOMECLAW_GROUNDER_URL",
    "HOMECLAW_OTEL_ENDPOINT",
)
ASSETS = (
    "deploy/compose.infrastructure.yaml",
    "deploy/postgres/001_workflow.sql",
    "deploy/postgres/002_registry.sql",
    "deploy/postgres/003_registry_outbox.sql",
    "deploy/mongodb/preferences-indexes.js",
    "deploy/grounder/compose.yaml",
    "docs/benchmark-protocol.md",
)


def _inside_repository(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != ROOT and ROOT in resolved.parents


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect external-acceptance prerequisites without connecting to services."
    )
    parser.add_argument("--output", default="reports/external-preflight.json")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when any optional prerequisite is absent",
    )
    args = parser.parse_args()

    output = Path(args.output)
    output = output if output.is_absolute() else ROOT / output
    if not _inside_repository(output):
        raise SystemExit("output must be a file inside the HomeClaw repository")

    module_status = {
        name: {
            "purpose": purpose,
            "available": _module_available(name),
        }
        for name, purpose in MODULES.items()
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read-only; no network, process start, or installation",
        "python_modules": module_status,
        "executables": {"docker": shutil.which("docker") is not None},
        "configuration": {name: bool(os.environ.get(name)) for name in CONFIG_NAMES},
        "repository_assets": {name: (ROOT / name).is_file() for name in ASSETS},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)

    complete = (
        all(item["available"] for item in module_status.values())
        and report["executables"]["docker"]
        and all(report["configuration"].values())
        and all(report["repository_assets"].values())
    )
    if args.strict and not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
