"""
Threshold Evaluator and Pattern Detection
"""
import uuid
import structlog
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from app.config import settings
from app.velocity.aggregator import VelocitySnapshot
from app.kafka.producer import producer_service

logger = structlog.get_logger(__name__)

class ThresholdEvaluator:
    
    @staticmethod
    async def evaluate(snapshot: VelocitySnapshot, txn_id: str):
        breaches = []
        patterns = []
        
        # 1-min checks
        if snapshot.txn_count_1m > settings.t1m_txn_count:
            breaches.append("1m_txn_count")
        if snapshot.txn_sum_1m > settings.t1m_txn_sum:
            breaches.append("1m_txn_sum")
        if snapshot.distinct_merchants_1m > settings.t1m_distinct_merchants:
            breaches.append("1m_distinct_merchants")
        if snapshot.distinct_countries_1m > settings.t1m_distinct_countries:
            breaches.append("1m_distinct_countries")
            
        # 5-min checks
        if snapshot.txn_count_5m > settings.t5m_txn_count:
            breaches.append("5m_txn_count")
            
        # 1-hr checks
        if snapshot.txn_count_1h > settings.t1h_txn_count:
            breaches.append("1h_txn_count")
            
        # 24-hr checks
        if snapshot.txn_count_24h > settings.t24h_txn_count:
            breaches.append("24h_txn_count")

        # Patterns
        # CARD_TESTING: >5 txn/min with distinct merchants
        if snapshot.txn_count_1m > 5 and snapshot.distinct_merchants_1m > 3 and snapshot.max_amount_1m < 10.0:
            patterns.append("CARD_TESTING")
            
        # GEO_ANOMALY: >1 country in 1-min
        if snapshot.distinct_countries_1m > 1:
            patterns.append("GEO_ANOMALY")
            
        # RAPID_FIRE: >3 in 1m (close enough to 30s)
        if snapshot.txn_count_1m > 3:
            patterns.append("RAPID_FIRE")
            
        # Publish breaches
        if breaches:
            payload = {
                "metadata": {
                    "event_id": f"evt_{uuid.uuid4()}",
                    "event_type": settings.velocity_breach_topic,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_service": settings.service_name
                },
                "payload": {
                    "customer_id": snapshot.customer_id,
                    "transaction_id": txn_id,
                    "breaches": breaches,
                    "snapshot": snapshot.__dict__
                }
            }
            await producer_service.publish(settings.velocity_breach_topic, snapshot.customer_id, payload)
            logger.warning("threshold.breach", customer_id=snapshot.customer_id, breaches=breaches)

        # Publish patterns
        if patterns:
            payload = {
                "metadata": {
                    "event_id": f"evt_{uuid.uuid4()}",
                    "event_type": settings.fraud_pattern_topic,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_service": settings.service_name
                },
                "payload": {
                    "customer_id": snapshot.customer_id,
                    "transaction_id": txn_id,
                    "patterns": patterns,
                    "snapshot": snapshot.__dict__
                }
            }
            await producer_service.publish(settings.fraud_pattern_topic, snapshot.customer_id, payload)
            logger.warning("pattern.detected", customer_id=snapshot.customer_id, patterns=patterns)
            
        # Always publish velocity snapshot
        payload = {
            "metadata": {
                "event_id": f"evt_{uuid.uuid4()}",
                "event_type": settings.velocity_updated_topic,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_service": settings.service_name
            },
            "payload": snapshot.__dict__
        }
        await producer_service.publish(settings.velocity_updated_topic, snapshot.customer_id, payload)
