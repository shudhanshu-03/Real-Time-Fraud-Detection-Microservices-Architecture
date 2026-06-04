"""
Customer Profile Main Application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.api.endpoints import router as api_router
from app.kafka.consumer import consumer_service
from app.database import engine, Base
import os

app = FastAPI(title="Customer Profile & Dashboard", version=settings.service_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Ensure dashboard dir exists for StaticFiles to mount
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
os.makedirs(dashboard_dir, exist_ok=True)
app.mount("/dashboard", StaticFiles(directory=dashboard_dir, html=True), name="dashboard")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    await consumer_service.start()

@app.on_event("shutdown")
async def shutdown_event():
    await consumer_service.stop()

@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}
