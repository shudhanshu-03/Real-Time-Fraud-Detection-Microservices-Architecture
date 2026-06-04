import json
import asyncio
from aiokafka import AIOKafkaConsumer
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.alert import Alert
from app.kafka.producer import producer_service

async def consume_alerts():
    consumer = AIOKafkaConsumer(
        settings.ALERT_TOPIC,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="alert-service-group",
        value_deserializer=lambda v: json.loads(v.decode('utf-8')) if v else {},
        auto_offset_reset="earliest"
    )
    
    await consumer.start()
    try:
        async for msg in consumer:
            if not msg.value: continue
            payload = msg.value.get("payload", {})
            transaction_id = payload.get("transaction_id")
            customer_id = payload.get("customer_id")
            score = payload.get("score", 0.0)
            
            if not transaction_id or not customer_id:
                continue
                
            async with AsyncSessionLocal() as db:
                new_alert = Alert(
                    transaction_id=transaction_id,
                    customer_id=customer_id,
                    score=score,
                    reason=f"Fraud score exceeded threshold: {score}"
                )
                db.add(new_alert)
                await db.commit()
                await db.refresh(new_alert)
                
                # Automatically escalate to a case if score is very high
                if score >= 0.8:
                    new_alert.status = "ESCALATED"
                    db.add(new_alert)
                    await db.commit()
                    
                    case_payload = {
                        "metadata": {
                            "event_type": "case.opened"
                        },
                        "payload": {
                            "alert_id": new_alert.alert_id,
                            "transaction_id": transaction_id,
                            "customer_id": customer_id,
                            "severity": "HIGH"
                        }
                    }
                    await producer_service.publish_event(
                        settings.CASE_TOPIC,
                        key=new_alert.alert_id,
                        payload=case_payload
                    )
    except asyncio.CancelledError:
        pass
    finally:
        await consumer.stop()

def start_kafka_consumer():
    loop = asyncio.get_event_loop()
    loop.create_task(consume_alerts())
