import json
import asyncio
from aiokafka import AIOKafkaConsumer
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.case import Case

async def consume_cases():
    consumer = AIOKafkaConsumer(
        settings.CASE_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="case-management-group",
        value_deserializer=lambda v: json.loads(v.decode('utf-8')) if v else {},
        auto_offset_reset="earliest"
    )
    
    await consumer.start()
    try:
        async for msg in consumer:
            if not msg.value: continue
            payload = msg.value.get("payload", {})
            alert_id = payload.get("alert_id")
            transaction_id = payload.get("transaction_id")
            customer_id = payload.get("customer_id")
            severity = payload.get("severity", "HIGH")
            
            if not alert_id or not transaction_id:
                continue
                
            async with AsyncSessionLocal() as db:
                new_case = Case(
                    alert_id=alert_id,
                    transaction_id=transaction_id,
                    customer_id=customer_id,
                    severity=severity
                )
                db.add(new_case)
                await db.commit()
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.stop()

def start_kafka_consumer():
    loop = asyncio.get_event_loop()
    loop.create_task(consume_cases())
