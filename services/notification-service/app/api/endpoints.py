"""
Notification API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models.notification import Notification

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/")
async def list_notifications(skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).offset(skip).limit(limit))
    notifications = result.scalars().all()
    return notifications


@router.get("/{notification_id}")
async def get_notification(notification_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification).filter(Notification.id == notification_id))
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


@router.get("/stats/summary")
async def get_stats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Notification.status))
    statuses = result.scalars().all()
    stats = {"PENDING": 0, "SENT": 0, "FAILED": 0, "DELIVERED": 0}
    for s in statuses:
        if s in stats:
            stats[s] += 1
    return stats
