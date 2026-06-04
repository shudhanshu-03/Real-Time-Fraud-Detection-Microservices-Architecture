from fastapi import APIRouter
import redis.asyncio as redis
from app.config import settings

router = APIRouter()
redis_client = redis.Redis(
    host=settings.redis_host, port=settings.redis_port, db=settings.redis_db, decode_responses=True
)


@router.get("/metrics")
async def get_metrics():
    try:
        total_tx = await redis_client.get("metrics:total_tx")
        fraud_tx = await redis_client.get("metrics:fraud_tx")
        blocked_tx = await redis_client.get("metrics:blocked_tx")
        total_volume = await redis_client.get("metrics:total_volume")

        return {
            "total_transactions": int(total_tx) if total_tx else 0,
            "fraud_transactions": int(fraud_tx) if fraud_tx else 0,
            "blocked_transactions": int(blocked_tx) if blocked_tx else 0,
            "total_volume": float(total_volume) if total_volume else 0.0,
        }
    except Exception as e:
        return {
            "error": str(e),
            "total_transactions": 0,
            "fraud_transactions": 0,
            "blocked_transactions": 0,
            "total_volume": 0.0,
        }
