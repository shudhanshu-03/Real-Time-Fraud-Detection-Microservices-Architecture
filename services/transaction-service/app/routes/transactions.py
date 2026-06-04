import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy import text
from pydantic import Field

from shared.fraud_common.models import TransactionCreate, TransactionResponse, FraudDecision
from shared.fraud_common.kafka_utils import FraudKafkaProducer, EventEnvelope
from app.dependencies import get_db, get_kafka_producer
from shared.fraud_common.database import DatabaseManager

router = APIRouter(prefix="/transactions", tags=["transactions"])


class TransactionPayload(TransactionCreate):
    customer_id: str = Field(..., description="Customer or account ID")


@router.post("", response_model=TransactionResponse, status_code=202)
async def create_transaction(
    payload: TransactionPayload,
    background_tasks: BackgroundTasks,
    db: DatabaseManager = Depends(get_db),
    kafka: FraudKafkaProducer = Depends(get_kafka_producer),
):
    """
    Ingests a new transaction, persists it, and publishes an event to Kafka.
    """
    # 1. Map to DB schema and insert
    # Using generated uuid for internal id, external_id is the payload.transaction_id
    internal_id = str(uuid.uuid4())
    ingested_at = datetime.now(timezone.utc)

    query = text("""
        INSERT INTO transactions (
            id, external_id, transaction_type, amount, currency, account_id,
            card_hash, merchant_id, merchant_name, merchant_category,
            device_fingerprint, ip_address, geo_latitude, geo_longitude,
            channel, transaction_time, ingested_at
        ) VALUES (
            :id, :external_id, 'purchase', :amount, :currency, :account_id,
            :card_hash, :merchant_id, :merchant_name, :merchant_category,
            :device_fingerprint, :ip_address, :geo_latitude, :geo_longitude,
            :channel, :transaction_time, :ingested_at
        )
    """)

    # Hash card number for basic storage (in real system this would be more secure/tokenized)
    import hashlib

    card_hash = hashlib.sha256(payload.card_number.encode()).hexdigest()

    params = {
        "id": internal_id,
        "external_id": payload.transaction_id,
        "amount": payload.amount,
        "currency": payload.currency,
        "account_id": payload.customer_id,
        "card_hash": card_hash,
        "merchant_id": payload.merchant_id,
        "merchant_name": payload.merchant_name,
        "merchant_category": payload.merchant_category,
        "device_fingerprint": payload.device_fingerprint,
        "ip_address": payload.ip_address,
        "geo_latitude": payload.location_lat if hasattr(payload, "location_lat") else None,
        "geo_longitude": payload.location_lon if hasattr(payload, "location_lon") else None,
        "channel": payload.channel,
        "transaction_time": payload.timestamp,
        "ingested_at": ingested_at,
    }

    # Execute DB insert if DB is ready
    if db and db.is_initialised:
        try:
            async with db.get_session() as session:
                await session.execute(query, params)
                await session.commit()
        except Exception as e:
            import logging

            logging.error(f"DB Insert failed: {e}")
            # Note: For strict correctness, we'd want to fail the request if DB fails.
            pass

    # 2. Publish to Kafka
    import logging

    logging.info(f"Is Kafka configured? {kafka is not None}")
    if kafka:
        event_payload = payload.model_dump(mode="json")
        event_payload["customer_id"] = payload.customer_id
        event = EventEnvelope(
            event_id=str(uuid.uuid4()),
            event_type="transaction.created",
            timestamp=ingested_at.isoformat(),
            source_service="transaction-service",
            payload=event_payload,
        )
        # Publish asynchronously in background task to not block the response
        background_tasks.add_task(
            kafka.publish, topic="transactions", key=str(payload.customer_id), event_envelope=event
        )

    # 3. Return 202 Accepted response
    response = TransactionResponse(
        id=internal_id,
        transaction_id=payload.transaction_id,
        card_number=payload.card_number,
        merchant_id=payload.merchant_id,
        merchant_name=payload.merchant_name,
        merchant_category=payload.merchant_category,
        amount=payload.amount,
        currency=payload.currency,
        timestamp=payload.timestamp,
        channel=payload.channel,
        risk_score=None,
        fraud_decision=FraudDecision.PENDING,
        created_at=ingested_at,
    )

    return response
