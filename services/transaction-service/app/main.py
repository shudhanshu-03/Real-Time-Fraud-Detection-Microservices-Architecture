import contextlib
from fastapi import FastAPI
from app.routes import transactions
from app.dependencies import db_manager
import app.dependencies as deps
from shared.fraud_common.kafka_utils import FraudKafkaProducer
from shared.fraud_common.database import DatabaseSettings
from app.config import settings

from dataclasses import dataclass

@dataclass
class DBDictSettings:
    database_dsn: str
    database_pool_size: int = 10
    database_pool_overflow: int = 20
    database_echo_sql: bool = False

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    await db_manager.create_engine(
        dsn=settings.database_url,
        pool_size=10,
        max_overflow=20
    )
    
    # Initialize Kafka
    deps.kafka_producer = FraudKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await deps.kafka_producer.start()
    
    yield
    
    # Cleanup
    if deps.kafka_producer:
        await deps.kafka_producer.stop()
    await db_manager.close()

app = FastAPI(title="Transaction Service", lifespan=lifespan)

app.include_router(transactions.router, prefix="/api/v1")

@app.get("/health")
def health(): return {"status": "ok"}
