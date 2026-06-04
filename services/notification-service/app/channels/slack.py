"""
Slack Channel
"""
import httpx
import structlog
from typing import List, Dict, Any
from app.config import settings

logger = structlog.get_logger(__name__)

class SlackChannel:
    @staticmethod
    async def send(webhook_url: str, blocks: List[Dict[str, Any]]) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    webhook_url,
                    json={"blocks": blocks},
                    timeout=5.0
                )
                response.raise_for_status()
            logger.info("slack.sent")
            return True
        except Exception as e:
            logger.error("slack.failed", error=str(e))
            return False
