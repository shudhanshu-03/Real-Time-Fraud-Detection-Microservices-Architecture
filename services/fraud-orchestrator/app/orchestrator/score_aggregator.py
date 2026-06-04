"""
Fraud Orchestrator - Score Aggregation.

Combines scores from multiple fraud-detection engines using configurable
weights and maps the final aggregate score to a FraudDecision.
"""

from __future__ import annotations

import structlog

from app.models.scoring import (
    DecisionThresholds,
    FraudDecision,
    ScoringWeights,
)

logger = structlog.get_logger(__name__)

# Maximum acceptable deviation when validating weight sums
_WEIGHT_SUM_TOLERANCE: float = 0.01


class ScoreAggregator:
    """Combines per-engine fraud scores into a single weighted score and
    translates the result into a categorical ``FraudDecision``.

    Usage::

        aggregator = ScoreAggregator()
        final = aggregator.aggregate(
            rule_score=0.4,
            ml_score=0.6,
            graph_score=0.2,
            historical_score=0.1,
            weights=ScoringWeights(),
        )
        decision = aggregator.make_decision(final, DecisionThresholds())
    """

    # --------------------------------------------------------------------- #
    # Aggregation
    # --------------------------------------------------------------------- #

    @staticmethod
    def aggregate(
        rule_score: float,
        ml_score: float,
        graph_score: float,
        historical_score: float,
        weights: ScoringWeights,
    ) -> float:
        """Compute the weighted aggregate fraud score.

        Args:
            rule_score: Score from the rule engine (0.0–1.0).
            ml_score: Score from the ML model (0.0–1.0).
            graph_score: Score from graph analysis (0.0–1.0).
            historical_score: Score from historical velocity data (0.0–1.0).
            weights: Weight configuration for each engine.

        Returns:
            Weighted sum clamped to the ``[0.0, 1.0]`` interval.

        Raises:
            ValueError: If any input score is outside ``[0.0, 1.0]`` or the
                weights do not sum to approximately 1.0.
        """
        # --- Validate individual scores ---
        scores = {
            "rule_score": rule_score,
            "ml_score": ml_score,
            "graph_score": graph_score,
            "historical_score": historical_score,
        }
        for name, value in scores.items():
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"{name} must be between 0.0 and 1.0, got {value}")

        # --- Validate weight sum ---
        weight_sum = weights.total
        if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"Scoring weights must sum to ~1.0 (got {weight_sum:.4f}). "
                f"Weights: rule={weights.w_rule}, ml={weights.w_ml}, "
                f"graph={weights.w_graph}, history={weights.w_history}"
            )

        # --- Weighted aggregation ---
        raw_score = (
            weights.w_rule * rule_score
            + weights.w_ml * ml_score
            + weights.w_graph * graph_score
            + weights.w_history * historical_score
        )
        final_score = max(0.0, min(1.0, raw_score))

        logger.info(
            "score_aggregation_complete",
            rule_score=rule_score,
            ml_score=ml_score,
            graph_score=graph_score,
            historical_score=historical_score,
            raw_score=round(raw_score, 6),
            final_score=round(final_score, 6),
            weights={
                "rule": weights.w_rule,
                "ml": weights.w_ml,
                "graph": weights.w_graph,
                "history": weights.w_history,
            },
        )

        return final_score

    # --------------------------------------------------------------------- #
    # Decision mapping
    # --------------------------------------------------------------------- #

    @staticmethod
    def make_decision(
        final_score: float,
        thresholds: DecisionThresholds,
    ) -> FraudDecision:
        """Map a final aggregate score to a categorical fraud decision.

        Decision logic::

            score <= thresholds.approve   → APPROVE
            score <= thresholds.review    → REVIEW
            score <= thresholds.high_risk → DECLINE
            score >  thresholds.high_risk → BLOCK

        Args:
            final_score: Weighted aggregate fraud score (0.0–1.0).
            thresholds: Configured decision thresholds.

        Returns:
            The appropriate ``FraudDecision``.
        """
        if final_score <= thresholds.approve:
            decision = FraudDecision.APPROVE
        elif final_score <= thresholds.review:
            decision = FraudDecision.REVIEW
        elif final_score <= thresholds.high_risk:
            decision = FraudDecision.DECLINE
        else:
            decision = FraudDecision.BLOCK

        logger.info(
            "fraud_decision_made",
            final_score=round(final_score, 6),
            decision=decision.value,
            thresholds={
                "approve": thresholds.approve,
                "review": thresholds.review,
                "high_risk": thresholds.high_risk,
            },
        )

        return decision
