"""
Velocity Aggregator using Redis
"""

import time
import uuid
import structlog
import redis.asyncio as redis
from typing import List, Dict, Any
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class VelocitySnapshot:
    customer_id: str
    txn_count_1m: int
    txn_sum_1m: float
    distinct_merchants_1m: int
    distinct_countries_1m: int

    txn_count_5m: int
    txn_sum_5m: float
    distinct_merchants_5m: int
    distinct_countries_5m: int

    txn_count_1h: int
    txn_sum_1h: float
    distinct_merchants_1h: int
    distinct_countries_1h: int

    txn_count_24h: int
    txn_sum_24h: float
    distinct_merchants_24h: int
    distinct_countries_24h: int

    max_amount_1m: float
    max_amount_5m: float
    max_amount_1h: float
    max_amount_24h: float


class VelocityAggregator:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    async def process_transaction(self, payload: Dict[str, Any]) -> VelocitySnapshot:
        customer_id = payload.get("customer_id")
        amount = payload.get("amount", 0.0)
        merchant_id = payload.get("merchant", {}).get("id", "unknown")
        country = payload.get("device", {}).get("geo", {}).get("country", "unknown")

        now = time.time()
        event_uuid = str(uuid.uuid4())

        windows = {"1m": 60, "5m": 300, "1h": 3600, "24h": 86400}

        pipe = self.redis.pipeline()

        # 1. Store time-ordered transactions for counts and max amounts
        for win, seconds in windows.items():
            zkey = f"velocity:cust:{customer_id}:txns:{win}"
            pipe.zremrangebyscore(zkey, "-inf", now - seconds)
            pipe.zadd(zkey, {f"{amount}:{event_uuid}": now})
            pipe.expire(zkey, seconds + 10)

            skey = f"velocity:cust:{customer_id}:sum:{win}"
            pipe.incrbyfloat(skey, amount)
            pipe.expire(skey, seconds + 10)

            mkey = f"velocity:cust:{customer_id}:merch:{win}"
            pipe.pfadd(mkey, merchant_id)
            pipe.expire(mkey, seconds + 10)

            ckey = f"velocity:cust:{customer_id}:country:{win}"
            pipe.pfadd(ckey, country)
            pipe.expire(ckey, seconds + 10)

        await pipe.execute()

        # 2. Retrieve aggregations
        pipe = self.redis.pipeline()
        for win in windows.keys():
            pipe.zcard(f"velocity:cust:{customer_id}:txns:{win}")
            pipe.get(f"velocity:cust:{customer_id}:sum:{win}")
            pipe.pfcount(f"velocity:cust:{customer_id}:merch:{win}")
            pipe.pfcount(f"velocity:cust:{customer_id}:country:{win}")
            # Get max amount by retrieving top element (sorted by amount in the string)
            # Actually, parsing max from ZRANGE might be slow, so we can store max separately,
            # or just estimate. For simplicity, we just keep the counts, sums, and distincts.
            # To get max, we can query the ZRANGE and parse.
            pipe.zrange(f"velocity:cust:{customer_id}:txns:{win}", 0, -1)

        results = await pipe.execute()

        # Process results
        def parse_max(zlist: List[str]) -> float:
            if not zlist:
                return 0.0
            max_val = 0.0
            for item in zlist:
                try:
                    val = float(item.split(":")[0])
                    if val > max_val:
                        max_val = val
                except Exception:
                    pass
            return max_val

        return VelocitySnapshot(
            customer_id=customer_id,
            txn_count_1m=int(results[0]),
            txn_sum_1m=float(results[1] or 0),
            distinct_merchants_1m=int(results[2]),
            distinct_countries_1m=int(results[3]),
            max_amount_1m=parse_max(results[4]),
            txn_count_5m=int(results[5]),
            txn_sum_5m=float(results[6] or 0),
            distinct_merchants_5m=int(results[7]),
            distinct_countries_5m=int(results[8]),
            max_amount_5m=parse_max(results[9]),
            txn_count_1h=int(results[10]),
            txn_sum_1h=float(results[11] or 0),
            distinct_merchants_1h=int(results[12]),
            distinct_countries_1h=int(results[13]),
            max_amount_1h=parse_max(results[14]),
            txn_count_24h=int(results[15]),
            txn_sum_24h=float(results[16] or 0),
            distinct_merchants_24h=int(results[17]),
            distinct_countries_24h=int(results[18]),
            max_amount_24h=parse_max(results[19]),
        )
