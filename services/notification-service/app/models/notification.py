"""
Notification Models
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id = Column(String, index=True, nullable=True)
    recipient_id = Column(String, index=True)
    channel = Column(String)  # email, sms, slack, webhook
    status = Column(String)   # PENDING, SENT, FAILED, DELIVERED
    subject = Column(String, nullable=True)
    body = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    attempts = relationship("DeliveryAttempt", back_populates="notification")

class DeliveryAttempt(Base):
    __tablename__ = "delivery_attempts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    notification_id = Column(String, ForeignKey("notifications.id"))
    attempt_number = Column(Integer)
    status = Column(String)
    response_code = Column(String, nullable=True)
    error_detail = Column(Text, nullable=True)
    attempted_at = Column(DateTime, default=datetime.utcnow)
    
    notification = relationship("Notification", back_populates="attempts")
