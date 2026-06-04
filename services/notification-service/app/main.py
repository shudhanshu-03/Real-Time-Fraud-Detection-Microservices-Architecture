"""
Notification Service Main Application
"""

from fastapi import FastAPI
from app.config import settings
from app.api.endpoints import router as api_router
from app.kafka.consumer import consumer_service
from app.kafka.producer import producer_service
from app.database import engine, Base

app = FastAPI(title="Notification Service", version=settings.service_version)

app.include_router(api_router)


@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await producer_service.start()
    await consumer_service.start()


@app.on_event("shutdown")
async def shutdown_event():
    await consumer_service.stop()
    await producer_service.stop()


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}
