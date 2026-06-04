"""
Notification Kafka Consumer
"""

import json
import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from app.config import settings
from app.dispatcher import NotificationDispatcher
from app.database import AsyncSessionLocal

logger = structlog.get_logger(__name__)


class ConsumerService:
    def __init__(self):
        self._consumer = None
        self._dispatcher = NotificationDispatcher(settings.redis_url)
        self._task = None

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            settings.notify_request_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else {},
            auto_offset_reset="earliest",
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self.consume())
        logger.info("kafka.consumer.started", topic=settings.notify_request_topic)

    async def consume(self):
        try:
            async for msg in self._consumer:
                if not msg.value:
                    continue
                payload = msg.value.get("payload", {})

                async with AsyncSessionLocal() as session:
                    await self._dispatcher.dispatch(payload, session)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("kafka.consumer.error", error=str(e))

    async def stop(self):
        if self._task:
            self._task.cancel()
        if self._consumer:
            await self._consumer.stop()
            logger.info("kafka.consumer.stopped")


consumer_service = ConsumerService()
