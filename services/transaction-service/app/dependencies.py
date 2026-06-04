from fastapi import Request
from shared.fraud_common.database import DatabaseManager, DatabaseSettings
from shared.fraud_common.kafka_utils import FraudKafkaProducer
from app.config import settings

# Global instances initialized in lifespan
db_manager = DatabaseManager()
kafka_producer: FraudKafkaProducer | None = None

def get_db():
    return db_manager

def get_kafka_producer():
    return kafka_producer
