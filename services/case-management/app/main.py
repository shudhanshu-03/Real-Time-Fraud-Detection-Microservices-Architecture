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
