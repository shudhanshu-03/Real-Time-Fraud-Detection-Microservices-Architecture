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
            "created_at": a.created_at,
        }
        for a in alerts
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
        "created_at": alert.created_at,
    }
