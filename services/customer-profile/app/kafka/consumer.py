"""
Customer Profile Kafka Consumer
"""

import json
import asyncio
import structlog
from aiokafka import AIOKafkaConsumer
from app.config import settings
from app.api.endpoints import notify_transaction, notify_alert

logger = structlog.get_logger(__name__)


class ConsumerService:
    def __init__(self):
        self._consumer = None
        self._task = None

    async def start(self):
        self._consumer = AIOKafkaConsumer(
            settings.transaction_enriched_topic,
            settings.fraud_scored_topic,
            settings.alert_created_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_consumer_group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else {},
            auto_offset_reset="latest",  # For dashboard, we only care about live data
        )
        await self._consumer.start()
        self._task = asyncio.create_task(self.consume())
        logger.info(
            "kafka.consumer.started",
            topics=[settings.transaction_enriched_topic, settings.fraud_scored_topic, settings.alert_created_topic],
        )

    async def consume(self):
        try:
            async for msg in self._consumer:
                if not msg.value:
                    continue
                payload = msg.value.get("payload", {})

                if msg.topic == settings.transaction_enriched_topic:
                    await notify_transaction({"type": "transaction", "data": payload})
                elif msg.topic == settings.fraud_scored_topic:
                    await notify_transaction({"type": "score", "data": payload})
                elif msg.topic == settings.alert_created_topic:
                    await notify_alert({"type": "alert", "data": payload})

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
