import os

def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip() + '\n')

base_alert = r"d:\project\Real Time Fraud Detection Microservices Architecture\services\alert-service"
base_case = r"d:\project\Real Time Fraud Detection Microservices Architecture\services\case-management"


# ALERT SERVICE

write_file(f'{base_alert}/Dockerfile', """
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8087"]
""")

write_file(f'{base_alert}/requirements.txt', """
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
aiokafka>=0.9.0
SQLAlchemy>=2.0.0
asyncpg>=0.29.0
greenlet>=3.0.0
structlog>=23.2.0
prometheus-client>=0.19.0
""")

write_file(f'{base_alert}/app/__init__.py', "")
write_file(f'{base_alert}/app/models/__init__.py', "")
write_file(f'{base_alert}/app/api/__init__.py', "")
write_file(f'{base_alert}/app/kafka/__init__.py', "")

write_file(f'{base_alert}/app/config.py', """
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "alert-service"
    PG_USER: str = "fraud_user"
    PG_PASSWORD: str = "fraud_pass"
    PG_HOST: str = "postgres"
    PG_PORT: int = 5432
    PG_DB: str = "fraud_transactions"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    ALERT_TOPIC: str = "alert.created"
    CASE_TOPIC: str = "case.opened"
    NOTIFY_TOPIC: str = "notification.requested"
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"

settings = Settings()
""")

write_file(f'{base_alert}/app/database.py', """
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
""")

write_file(f'{base_alert}/app/models/alert.py', """
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime
from app.database import Base

class Alert(Base):
    __tablename__ = "alerts"
    
    alert_id = Column(String, primary_key=True, default=lambda: f"alt_{uuid.uuid4().hex[:16]}")
    transaction_id = Column(String, nullable=False, index=True)
    customer_id = Column(String, nullable=False, index=True)
    score = Column(Float, nullable=False)
    status = Column(String, default="NEW") # NEW, ESCALATED, CLOSED
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
""")

write_file(f'{base_alert}/app/api/endpoints.py', """
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any
from app.database import get_db
from app.models.alert import Alert

router = APIRouter()

@router.get("/alerts", response_model=List[Dict[str, Any]])
async def list_alerts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).limit(100))
    alerts = result.scalars().all()
    return [
        {
            "alert_id": a.alert_id,
            "transaction_id": a.transaction_id,
            "customer_id": a.customer_id,
            "score": a.score,
            "status": a.status,
            "created_at": a.created_at
        } for a in alerts
    ]
    
@router.get("/alerts/{alert_id}")
async def get_alert(alert_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).filter(Alert.alert_id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        "alert_id": alert.alert_id,
        "transaction_id": alert.transaction_id,
        "customer_id": alert.customer_id,
        "score": alert.score,
        "status": alert.status,
        "reason": alert.reason,
        "created_at": alert.created_at
    }
""")

write_file(f'{base_alert}/app/kafka/producer.py', """
import json
from aiokafka import AIOKafkaProducer
from app.config import settings

class KafkaProducerService:
    def __init__(self):
        self.producer = None

    async def start(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await self.producer.start()

    async def stop(self):
        if self.producer:
            await self.producer.stop()

    async def publish_event(self, topic: str, key: str, payload: dict):
        if self.producer:
            await self.producer.send_and_wait(
                topic=topic,
                key=key.encode('utf-8'),
                value=payload
            )

producer_service = KafkaProducerService()
""")

write_file(f'{base_alert}/app/kafka/consumer.py', """
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
""")

write_file(f'{base_alert}/app/main.py', """
from fastapi import FastAPI
from app.api.endpoints import router as api_router
from app.database import engine, Base
from app.kafka.producer import producer_service
from app.kafka.consumer import start_kafka_consumer

app = FastAPI(title="Alert Service", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await producer_service.start()
    start_kafka_consumer()

@app.on_event("shutdown")
async def shutdown_event():
    await producer_service.stop()
    await engine.dispose()

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok", "service": "alert-service"}
""")

# ---------------------------------------------------------
# CASE MANAGEMENT SERVICE
# ---------------------------------------------------------

write_file(f'{base_case}/Dockerfile', """
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
""")

write_file(f'{base_case}/requirements.txt', """
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
aiokafka>=0.9.0
SQLAlchemy>=2.0.0
asyncpg>=0.29.0
greenlet>=3.0.0
structlog>=23.2.0
prometheus-client>=0.19.0
""")

write_file(f'{base_case}/app/__init__.py', "")
write_file(f'{base_case}/app/models/__init__.py', "")
write_file(f'{base_case}/app/api/__init__.py', "")
write_file(f'{base_case}/app/kafka/__init__.py', "")

write_file(f'{base_case}/app/config.py', """
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_NAME: str = "case-management"
    PG_USER: str = "fraud_user"
    PG_PASSWORD: str = "fraud_pass"
    PG_HOST: str = "postgres"
    PG_PORT: int = 5432
    PG_DB: str = "fraud_transactions"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    CASE_TOPIC: str = "case.opened"
    
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"

settings = Settings()
""")

write_file(f'{base_case}/app/database.py', """
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
""")

write_file(f'{base_case}/app/models/case.py', """
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Case(Base):
    __tablename__ = "cases"
    
    case_id = Column(String, primary_key=True, default=lambda: f"cas_{uuid.uuid4().hex[:16]}")
    alert_id = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    severity = Column(String, default="HIGH")
    status = Column(String, default="OPEN") # OPEN, IN_PROGRESS, CLOSED_FRAUD, CLOSED_FALSE_POSITIVE
    assigned_to = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    notes = relationship("CaseNote", back_populates="case")

class CaseNote(Base):
    __tablename__ = "case_notes"
    
    note_id = Column(String, primary_key=True, default=lambda: f"not_{uuid.uuid4().hex[:16]}")
    case_id = Column(String, ForeignKey("cases.case_id"))
    author = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    case = relationship("Case", back_populates="notes")
""")

write_file(f'{base_case}/app/api/endpoints.py', """
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List, Dict, Any
from app.database import get_db
from app.models.case import Case, CaseNote
from pydantic import BaseModel

router = APIRouter()

class NoteCreate(BaseModel):
    author: str
    content: str

class CaseUpdate(BaseModel):
    status: str
    assigned_to: str = None

@router.get("/cases")
async def list_cases(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).limit(100))
    cases = result.scalars().all()
    return [
        {
            "case_id": c.case_id,
            "alert_id": c.alert_id,
            "transaction_id": c.transaction_id,
            "customer_id": c.customer_id,
            "status": c.status,
            "severity": c.severity,
            "assigned_to": c.assigned_to,
            "created_at": c.created_at
        } for c in cases
    ]

@router.get("/cases/{case_id}")
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    notes_result = await db.execute(select(CaseNote).filter(CaseNote.case_id == case_id))
    notes = notes_result.scalars().all()
    
    return {
        "case_id": case.case_id,
        "alert_id": case.alert_id,
        "transaction_id": case.transaction_id,
        "customer_id": case.customer_id,
        "status": case.status,
        "severity": case.severity,
        "assigned_to": case.assigned_to,
        "created_at": case.created_at,
        "notes": [
            {
                "note_id": n.note_id,
                "author": n.author,
                "content": n.content,
                "created_at": n.created_at
            } for n in notes
        ]
    }

@router.post("/cases/{case_id}/notes")
async def add_case_note(case_id: str, note: NoteCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    new_note = CaseNote(
        case_id=case_id,
        author=note.author,
        content=note.content
    )
    db.add(new_note)
    await db.commit()
    return {"status": "success", "note_id": new_note.note_id}

@router.patch("/cases/{case_id}")
async def update_case(case_id: str, update_data: CaseUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Case).filter(Case.case_id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
        
    case.status = update_data.status
    if update_data.assigned_to:
        case.assigned_to = update_data.assigned_to
        
    db.add(case)
    await db.commit()
    return {"status": "success", "case_id": case.case_id}
""")

write_file(f'{base_case}/app/kafka/consumer.py', """
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
""")

write_file(f'{base_case}/app/main.py', """
from fastapi import FastAPI
from app.api.endpoints import router as api_router
from app.database import engine, Base
from app.kafka.consumer import start_kafka_consumer

app = FastAPI(title="Case Management Service", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    start_kafka_consumer()

@app.on_event("shutdown")
async def shutdown_event():
    await engine.dispose()

app.include_router(api_router, prefix="/api/v1")

@app.get("/health")
def health():
    return {"status": "ok", "service": "case-management"}
""")

print("Successfully created alert-service and case-management service files.")
