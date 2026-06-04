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
    status = Column(String, default="NEW")  # NEW, ESCALATED, CLOSED
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
