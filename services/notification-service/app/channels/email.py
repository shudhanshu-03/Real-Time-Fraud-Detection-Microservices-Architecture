"""
Email Channel
"""
import structlog
import aiosmtplib
from email.message import EmailMessage
from app.config import settings

logger = structlog.get_logger(__name__)

class EmailChannel:
    @staticmethod
    async def send(recipient: str, subject: str, html_body: str) -> bool:
        message = EmailMessage()
        message["From"] = settings.smtp_from
        message["To"] = recipient
        message["Subject"] = subject
        message.add_alternative(html_body, subtype="html")

        try:
            # In a real app we would use aiosmtplib.send
            # await aiosmtplib.send(
            #     message,
            #     hostname=settings.smtp_host,
            #     port=settings.smtp_port,
            #     username=settings.smtp_user,
            #     password=settings.smtp_pass,
            #     use_tls=True
            # )
            logger.info("email.sent", recipient=recipient, subject=subject)
            return True
        except Exception as e:
            logger.error("email.failed", recipient=recipient, error=str(e))
            return False
