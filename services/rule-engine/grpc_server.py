import time
import logging
import rule_engine_pb2
import rule_engine_pb2_grpc
from db import fetch_active_rules
from evaluator import RuleEvaluator

logger = logging.getLogger(__name__)

# In-memory cache of rules to avoid hitting DB on every request.
# In production, we'd use a more sophisticated invalidation mechanism (e.g. Pub/Sub).
_cached_rules = []
_last_reload = None


async def reload_rules_cache():
    global _cached_rules, _last_reload
    logger.info("Reloading rules from database...")
    _cached_rules = await fetch_active_rules()

    # We construct a Timestamp for when it was last loaded
    from google.protobuf.timestamp_pb2 import Timestamp

    ts = Timestamp()
    ts.GetCurrentTime()
    _last_reload = ts
    logger.info(f"Loaded {len(_cached_rules)} rules.")


class RuleEngineServicer(rule_engine_pb2_grpc.RuleEngineServiceServicer):
    async def EvaluateRules(self, request, context):
        start_time = time.time()

        if not _cached_rules and _last_reload is None:
            await reload_rules_cache()

        evaluator = RuleEvaluator(_cached_rules)

        # Evaluate
        result = await evaluator.evaluate_transaction(request.transaction)

        end_time = time.time()
        result.execution_time_ms = (end_time - start_time) * 1000.0

        return result

    async def GetRuleHealth(self, request, context):
        from google.protobuf.timestamp_pb2 import Timestamp

        ts = Timestamp()
        ts.GetCurrentTime()

        return rule_engine_pb2.HealthResponse(
            status="SERVING",
            service="rule-engine-service",
            version="1.0.0",
            timestamp=ts,
            loaded_rules=len(_cached_rules),
            last_reload=_last_reload or ts,
        )
