"""
Stream Processor Kafka Producer
"""
import json
import structlog
from typing import Dict, Any, Optional
from aiokafka import AIOKafkaProducer
from app.config import settings

logger = structlog.get_logger(__name__)

class ProducerService:
    def __init__(self):
        self._producer: Optional[AIOKafkaProducer] = None

    async def start(self):
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            client_id=f"{settings.service_name}-producer",
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        await self._producer.start()
        logger.info("kafka.producer.started", bootstrap_servers=settings.kafka_bootstrap_servers)

    async def stop(self):
        if self._producer:
            await self._producer.stop()
            logger.info("kafka.producer.stopped")

    async def publish(self, topic: str, key: str, payload: Dict[str, Any]):
        if not self._producer:
            logger.error("kafka.producer.not_started")
            return
            
        try:
            await self._producer.send_and_wait(
                topic,
                key=key,
                value=payload
            )
            logger.debug("kafka.producer.message_sent", topic=topic, key=key)
        except Exception as e:
            logger.error("kafka.producer.send_failed", topic=topic, key=key, error=str(e))

producer_service = ProducerService()
