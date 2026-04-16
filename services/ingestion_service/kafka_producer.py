"""Async Kafka producer wrapper for document messages."""
from __future__ import annotations

import json
import logging

from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)


class DocumentProducer:
    """Thin async wrapper around AIOKafkaProducer."""

    def __init__(self, bootstrap_servers: str, topic: str) -> None:
        self._bootstrap = bootstrap_servers
        self._topic = topic
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap,
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode() if isinstance(k, str) else k,
            compression_type="gzip",
            acks="all",
            max_request_size=52428800,
        )
        await self._producer.start()
        logger.info("Kafka producer connected to %s, topic=%s", self._bootstrap, self._topic)

    async def stop(self) -> None:
        if self._producer:
            await self._producer.stop()

    async def send(self, message: dict, key: str | None = None) -> None:
        if not self._producer:
            raise RuntimeError("Producer not started")
        await self._producer.send_and_wait(self._topic, value=message, key=key)
        logger.debug("Sent doc_id=%s to topic=%s", key, self._topic)
