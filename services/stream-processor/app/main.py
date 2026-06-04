"""
Stream Processor Main Application
"""

from fastapi import FastAPI
from app.config import settings
from app.kafka.consumer import consumer_service
from app.kafka.producer import producer_service

app = FastAPI(title="Stream Processor Service", version=settings.service_version)


@app.on_event("startup")
async def startup_event():
    await producer_service.start()
    await consumer_service.start()


@app.on_event("shutdown")
async def shutdown_event():
    await consumer_service.stop()
    await producer_service.stop()


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}
