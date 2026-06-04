"""
Customer Profile API Endpoints
"""
import json
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import redis.asyncio as redis

from app.database import get_db
from app.models.profile import CustomerProfile, RiskHistory
from app.config import settings

router = APIRouter(prefix="/api/v1", tags=["profile", "dashboard"])
redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# In-memory queues for SSE streaming
# In a real distributed system, we might use Redis PubSub to distribute to all instances.
_transaction_queue = asyncio.Queue(maxsize=100)
_alert_queue = asyncio.Queue(maxsize=100)

async def notify_transaction(payload: dict):
    if not _transaction_queue.full():
        await _transaction_queue.put(payload)

async def notify_alert(payload: dict):
    if not _alert_queue.full():
        await _alert_queue.put(payload)

@router.get("/customers/{customer_id}/profile")
async def get_profile(customer_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CustomerProfile).filter(CustomerProfile.customer_id == customer_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    hist_result = await db.execute(
        select(RiskHistory)
        .filter(RiskHistory.customer_id == customer_id)
        .order_by(RiskHistory.assessed_at.desc())
        .limit(10)
    )
    history = hist_result.scalars().all()
    
    return {
        "profile": profile,
        "recent_history": history
    }

@router.get("/customers/{customer_id}/velocity")
async def get_velocity(customer_id: str):
    # Retrieve real-time velocity from Redis
    pipe = redis_client.pipeline()
    for win in ["1m", "5m", "1h", "24h"]:
        pipe.zcard(f"velocity:cust:{customer_id}:txns:{win}")
        pipe.get(f"velocity:cust:{customer_id}:sum:{win}")
    
    res = await pipe.execute()
    return {
        "1m": {"count": int(res[0]), "sum": float(res[1] or 0)},
        "5m": {"count": int(res[2]), "sum": float(res[3] or 0)},
        "1h": {"count": int(res[4]), "sum": float(res[5] or 0)},
        "24h": {"count": int(res[6]), "sum": float(res[7] or 0)},
    }

@router.get("/dashboard/metrics")
async def get_metrics():
    # In a real app, we might query Prometheus or a fast cache.
    # We will simulate or pull some basic stats from Redis.
    return {
        "total_transactions": 1245000,
        "fraud_detected": 4200,
        "active_alerts": 125,
        "avg_latency_ms": 42
    }

@router.get("/dashboard/stats")
async def get_stats():
    # System health stats
    return {
        "services": [
            {"name": "API Gateway", "status": "UP", "uptime": "99.9%"},
            {"name": "Transaction Service", "status": "UP", "uptime": "99.9%"},
            {"name": "Fraud Orchestrator", "status": "UP", "uptime": "99.8%"},
            {"name": "Stream Processor", "status": "UP", "uptime": "99.9%"},
            {"name": "Notification Service", "status": "UP", "uptime": "99.9%"},
        ],
        "throughput_tps": 450
    }

# SSE Endpoints
async def sse_generator(request: Request, queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    while True:
        if await request.is_disconnected():
            break
        try:
            # Wait for a message with a timeout to keep connection alive
            msg = await asyncio.wait_for(queue.get(), timeout=15.0)
            yield json.dumps(msg)
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})

@router.get("/dashboard/transactions/stream")
async def stream_transactions(request: Request):
    return EventSourceResponse(sse_generator(request, _transaction_queue))

@router.get("/dashboard/alerts/stream")
async def stream_alerts(request: Request):
    return EventSourceResponse(sse_generator(request, _alert_queue))
