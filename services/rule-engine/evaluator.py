import logging
from typing import Dict, Any, List, Optional
import redis_client
import rule_engine_pb2

logger = logging.getLogger(__name__)

class RuleEvaluator:
    def __init__(self, rules: List[Dict[str, Any]]):
        self.rules = rules

    async def evaluate_transaction(self, ctx: rule_engine_pb2.TransactionContext) -> rule_engine_pb2.RuleEvalResult:
        result = rule_engine_pb2.RuleEvalResult()
        result.rules_evaluated = len(self.rules)
        
        total_score = 0.0
        
        for rule in self.rules:
            is_match = False
            match_description = ""
            
            try:
                is_match, match_description = await self._evaluate_rule(rule["conditions"], ctx)
            except Exception as e:
                logger.error(f"Error evaluating rule {rule['rule_name']}: {str(e)}")
                continue

            if is_match:
                rule_match = result.triggered_rules.add()
                rule_match.rule_id = str(rule["id"])
                rule_match.rule_name = rule["rule_name"]
                rule_match.severity = rule["severity"]
                rule_match.score = rule["score_contribution"]
                rule_match.description = match_description
                rule_match.category = rule["category"]
                
                total_score += rule["score_contribution"]
                result.rules_matched += 1

                if rule["severity"] == "CRITICAL":
                    # Short-circuit on critical
                    break

        result.rule_score = min(total_score, 1.0)
        return result

    async def _evaluate_rule(self, conditions: Dict[str, Any], ctx: rule_engine_pb2.TransactionContext) -> (bool, str):
        condition_type = conditions.get("type")

        if condition_type == "condition":
            return self._evaluate_simple_condition(conditions, ctx)
        elif condition_type == "velocity":
            return await self._evaluate_velocity(conditions, ctx)
        
        return False, ""

    def _evaluate_simple_condition(self, conditions: Dict[str, Any], ctx: rule_engine_pb2.TransactionContext) -> (bool, str):
        field = conditions.get("field")
        operator = conditions.get("operator")
        value = conditions.get("value")
        
        # Determine actual value of the field from context
        ctx_value = getattr(ctx, field, None)
        
        if "value_field" in conditions:
            value = getattr(ctx, conditions["value_field"], None)
            
        if ctx_value is None or value is None:
            return False, ""

        is_match = False
        if operator == ">":
            is_match = ctx_value > value
        elif operator == "<":
            is_match = ctx_value < value
        elif operator == "==":
            is_match = ctx_value == value
        elif operator == "!=":
            is_match = ctx_value != value
        elif operator == ">=":
            is_match = ctx_value >= value
        elif operator == "<=":
            is_match = ctx_value <= value
            
        description = f"{field} {operator} {value}" if is_match else ""
        return is_match, description

    async def _evaluate_velocity(self, conditions: Dict[str, Any], ctx: rule_engine_pb2.TransactionContext) -> (bool, str):
        entity = conditions.get("entity") # e.g. "card_number"
        window_seconds = conditions.get("window_seconds", 86400)
        limit = conditions.get("limit", 5)
        
        entity_value = getattr(ctx, entity, None)
        if not entity_value:
            return False, ""
            
        is_exceeded = await redis_client.check_velocity(entity, entity_value, window_seconds, limit)
        
        description = f"Velocity exceeded limit {limit} within {window_seconds}s for {entity}" if is_exceeded else ""
        return is_exceeded, description
