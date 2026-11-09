"""Optional aio-pika adapter for service-split deployments.

Importing this module does not require aio-pika.  The dependency is loaded only
when ``connect`` is invoked by a configured deployment.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Awaitable, Callable

from homeclaw.domain import CONTRACT_VERSION, CorrelationIds, MessageEnvelope


class AioPikaEventBus:
    def __init__(self, url: str, exchange_name: str = "homeclaw.events") -> None:
        self.url = url
        self.exchange_name = exchange_name
        self.connection = None
        self.channel = None
        self.exchange = None
        self._aio_pika = None

    async def connect(self) -> None:
        try:
            import aio_pika
        except ImportError as exc:
            raise RuntimeError("aio-pika is required only for RabbitMQ deployment") from exc
        self._aio_pika = aio_pika
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel(publisher_confirms=True)
        await self.channel.set_qos(prefetch_count=16)
        self.exchange = await self.channel.declare_exchange(
            self.exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )

    async def publish(self, routing_key: str, envelope: MessageEnvelope) -> None:
        if self.exchange is None or self._aio_pika is None:
            raise RuntimeError("RabbitMQ event bus is not connected")
        message = self._aio_pika.Message(
            body=json.dumps(envelope.to_dict(), separators=(",", ":")).encode("utf-8"),
            content_type="application/json",
            delivery_mode=self._aio_pika.DeliveryMode.PERSISTENT,
            message_id=envelope.message_id,
            correlation_id=envelope.ids.request_id,
            headers={
                "schema_version": envelope.schema_version,
                "trace_id": envelope.ids.trace_id,
                "task_id": envelope.ids.task_id,
            },
        )
        await self.exchange.publish(message, routing_key=routing_key, mandatory=True)

    async def consume(
        self,
        queue_name: str,
        routing_key: str,
        handler: Callable[[MessageEnvelope], Awaitable[None]],
    ) -> Any:
        if self.channel is None or self.exchange is None:
            raise RuntimeError("RabbitMQ event bus is not connected")
        dead_letter_exchange = await self.channel.declare_exchange(
            f"{self.exchange_name}.dead",
            self._aio_pika.ExchangeType.TOPIC,
            durable=True,
        )
        dead_letter_queue = await self.channel.declare_queue(
            f"{queue_name}.dead",
            durable=True,
            arguments={"x-queue-type": "quorum"},
        )
        await dead_letter_queue.bind(dead_letter_exchange, routing_key=routing_key)
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-dead-letter-exchange": f"{self.exchange_name}.dead",
                "x-dead-letter-routing-key": routing_key,
            },
        )
        await queue.bind(self.exchange, routing_key=routing_key)

        async def on_message(message: Any) -> None:
            async with message.process(requeue=False):
                raw = json.loads(message.body.decode("utf-8"))
                envelope = self.decode_envelope(raw)
                await handler(envelope)

        return await queue.consume(on_message, no_ack=False)

    @staticmethod
    def decode_envelope(raw: Any) -> MessageEnvelope:
        if not isinstance(raw, dict):
            raise ValueError("event envelope must be a JSON object")
        schema_version = str(raw.get("schema_version", ""))
        if schema_version != CONTRACT_VERSION:
            raise ValueError(
                f"unsupported event schema_version: {schema_version or 'missing'}"
            )
        ids = raw["ids"]
        return MessageEnvelope(
            message_type=raw["message_type"],
            ids=CorrelationIds(
                ids["trace_id"], ids["request_id"], ids["task_id"], ids.get("command_id")
            ),
            payload=raw["payload"],
            producer=raw["producer"],
            message_id=raw["message_id"],
            created_at=datetime.fromisoformat(raw["created_at"]),
            schema_version=schema_version,
        )

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
