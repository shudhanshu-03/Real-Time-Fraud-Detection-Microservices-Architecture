"""
Notification Dispatcher
"""
import uuid
import structlog
from datetime import datetime
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.models.notification import Notification, DeliveryAttempt
from app.channels.email import EmailChannel
from app.channels.sms import SMSChannel
from app.channels.slack import SlackChannel
from app.channels.webhook import WebhookChannel
from app.templates import EMAIL_TEMPLATE, SMS_TEMPLATE, get_slack_blocks

logger = structlog.get_logger(__name__)

class NotificationDispatcher:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
    async def dispatch(self, payload: dict, session: AsyncSession) -> bool:
        recipient_id = payload.get("recipient_id")
        alert_id = payload.get("alert_id")
        severity = payload.get("severity", "LOW")
        
        # Deduplication
        dedup_key = f"notify:dedup:{recipient_id}:{alert_id}"
        is_duplicate = await self.redis.get(dedup_key)
        if is_duplicate:
            logger.info("dispatch.skipped_duplicate", recipient_id=recipient_id, alert_id=alert_id)
            return False
            
        await self.redis.set(dedup_key, "1", ex=86400) # 24h dedup window
        
        # Determine channels
        channels = ["email"]
        if severity == "CRITICAL":
            channels.extend(["sms", "slack", "webhook"])
        elif severity == "HIGH":
            channels.extend(["slack", "webhook"])
        elif severity == "MEDIUM":
            channels.extend(["webhook"])
            
        transaction_id = payload.get("transaction_id", "Unknown")
        amount = payload.get("amount", "Unknown")
        merchant = payload.get("merchant", "Unknown")
        risk_score = payload.get("risk_score", "Unknown")
        
        for ch in channels:
            notification = Notification(
                alert_id=alert_id,
                recipient_id=recipient_id,
                channel=ch,
                status="PENDING",
                subject=f"Fraud Alert: {severity}",
                body="Alert content"
            )
            session.add(notification)
            await session.commit()
            await session.refresh(notification)
            
            attempt = DeliveryAttempt(notification_id=notification.id, attempt_number=1, status="PENDING")
            session.add(attempt)
            
            success = False
            try:
                if ch == "email":
                    html = EMAIL_TEMPLATE.format(
                        severity=severity, alert_id=alert_id, transaction_id=transaction_id,
                        amount=amount, merchant=merchant, risk_score=risk_score
                    )
                    success = await EmailChannel.send("customer@example.com", notification.subject, html)
                elif ch == "sms":
                    msg = SMS_TEMPLATE.format(transaction_id=transaction_id, amount=amount, merchant=merchant)
                    success = await SMSChannel.send("+1234567890", msg)
                elif ch == "slack":
                    blocks = get_slack_blocks(alert_id, severity, amount, merchant, risk_score)
                    success = await SlackChannel.send(settings.slack_webhook_url, blocks)
                elif ch == "webhook":
                    success = await WebhookChannel.send("https://example.com/webhook", payload, "secret")
                    
                if success:
                    notification.status = "SENT"
                    notification.sent_at = datetime.utcnow()
                    attempt.status = "SUCCESS"
                else:
                    notification.status = "FAILED"
                    attempt.status = "FAILED"
            except Exception as e:
                notification.status = "FAILED"
                notification.error_message = str(e)
                attempt.status = "FAILED"
                attempt.error_detail = str(e)
                
            await session.commit()
            
        return True
