"""
Customer Profile Models
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Float, Text, JSON
from sqlalchemy.orm import relationship
from app.database import Base

class CustomerProfile(Base):
    __tablename__ = "customer_profiles"
    
    customer_id = Column(String, primary_key=True)
    email = Column(String, nullable=True)
    name = Column(String, nullable=True)
    risk_level = Column(String, default="LOW") # LOW/MEDIUM/HIGH/CRITICAL
    total_transactions = Column(Integer, default=0)
    total_fraud_flags = Column(Integer, default=0)
    avg_transaction_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    risk_history = relationship("RiskHistory", back_populates="profile")
    patterns = relationship("TransactionPattern", back_populates="profile")

class RiskHistory(Base):
    __tablename__ = "risk_history"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customer_profiles.customer_id"))
    risk_score = Column(Float)
    risk_level = Column(String)
    triggered_rules = Column(JSON, nullable=True)
    assessed_at = Column(DateTime, default=datetime.utcnow)
    
    profile = relationship("CustomerProfile", back_populates="risk_history")

class TransactionPattern(Base):
    __tablename__ = "transaction_patterns"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id = Column(String, ForeignKey("customer_profiles.customer_id"))
    pattern_type = Column(String)
    description = Column(Text, nullable=True)
    frequency = Column(Integer, default=1)
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    
    profile = relationship("CustomerProfile", back_populates="patterns")
