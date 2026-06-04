import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class Case(Base):
    __tablename__ = "cases"
    
    case_id = Column(String, primary_key=True, default=lambda: f"cas_{uuid.uuid4().hex[:16]}")
    alert_id = Column(String, nullable=False, index=True)
    transaction_id = Column(String, nullable=False)
    customer_id = Column(String, nullable=False)
    severity = Column(String, default="HIGH")
    status = Column(String, default="OPEN") # OPEN, IN_PROGRESS, CLOSED_FRAUD, CLOSED_FALSE_POSITIVE
    assigned_to = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    notes = relationship("CaseNote", back_populates="case")

class CaseNote(Base):
    __tablename__ = "case_notes"
    
    note_id = Column(String, primary_key=True, default=lambda: f"not_{uuid.uuid4().hex[:16]}")
    case_id = Column(String, ForeignKey("cases.case_id"))
    author = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    case = relationship("Case", back_populates="notes")
