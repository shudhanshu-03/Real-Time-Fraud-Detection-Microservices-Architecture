"""
Webhook Channel
"""

import hmac
import hashlib
import json
import httpx
import structlog
from typing import Dict, Any

logger = structlog.get_logger(__name__)


class WebhookChannel:
    @staticmethod
    async def send(url: str, payload: Dict[str, Any], secret: str) -> bool:
        try:
            payload_bytes = json.dumps(payload).encode("utf-8")
            signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    content=payload_bytes,
                    headers={"Content-Type": "application/json", "X-Signature": signature},
                    timeout=5.0,
                )
                response.raise_for_status()
            logger.info("webhook.sent", url=url)
            return True
        except Exception as e:
            logger.error("webhook.failed", url=url, error=str(e))
            return False
