"""
Fraud Orchestrator - Pydantic Scoring Models.

Domain models for the scoring pipeline including requests, engine results,
aggregated scoring outcomes, and fraud decision enumerations.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class FraudDecision(str, enum.Enum):
    """Enumeration of possible fraud decisions."""

    APPROVE = "approve"
    REVIEW = "review"
    DECLINE = "decline"
    BLOCK = "block"


class ScoringWeights(BaseModel):
    """Weights applied to each scoring engine during aggregation.

    The four weights must sum to approximately 1.0 (tolerance ±0.01).
    """

    w_rule: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Weight for the rule-engine score",
    )
    w_ml: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight for the ML scoring model",
    )
    w_graph: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight for the graph-analysis score",
    )
    w_history: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Weight for the historical velocity score",
    )

    @property
    def total(self) -> float:
        """Return the sum of all weights."""
        return self.w_rule + self.w_ml + self.w_graph + self.w_history


class DecisionThresholds(BaseModel):
    """Thresholds that map a final score to a FraudDecision.

    - score <= approve  → APPROVE
    - score <= review   → REVIEW
    - score <= high_risk → DECLINE
    - score > high_risk  → BLOCK
    """

    approve: float = Field(
        default=0.30,
        ge=0.0,
        le=1.0,
        description="Maximum score to auto-approve",
    )
    review: float = Field(
        default=0.60,
        ge=0.0,
        le=1.0,
        description="Maximum score to flag for manual review",
    )
    high_risk: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum score to block the transaction",
    )


class ScoringRequest(BaseModel):
    """Inbound transaction data that must be scored for fraud risk.

    Fields mirror the upstream ``transaction.created`` Kafka event payload.
    """

    transaction_id: UUID = Field(
        ...,
        description="Unique identifier of the transaction",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount in the given currency",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 currency code",
    )
    account_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the payer account",
    )
    merchant_id: str = Field(
        ...,
        min_length=1,
        description="Identifier of the merchant",
    )
    merchant_category: str = Field(
        ...,
        description="Merchant category code or label",
    )
    merchant_country: str = Field(
        ...,
        description="ISO 3166-1 alpha-2 country code of the merchant",
    )
    device_id: str = Field(
        ...,
        description="Identifier of the originating device",
    )
    device_type: str = Field(
        ...,
        description="Device type (e.g. mobile, desktop, pos_terminal)",
    )
    ip_address: str = Field(
        ...,
        description="IP address of the originating request",
    )
    channel: str = Field(
        ...,
        description="Transaction channel (e.g. online, in_store, atm)",
    )
    entry_mode: str = Field(
        ...,
        description="Card entry mode (e.g. chip, swipe, contactless, manual)",
    )
    is_international: bool = Field(
        default=False,
        description="Whether the transaction crosses national borders",
    )
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Latitude of the transaction location",
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Longitude of the transaction location",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Arbitrary additional metadata from the upstream event",
    )


class EngineResult(BaseModel):
    """Result returned by a single scoring engine (rule, ML, graph, etc.)."""

    engine_name: str = Field(
        ...,
        description="Name of the scoring engine that produced this result",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Risk score produced by the engine (0=safe, 1=fraud)",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence of the engine in its score",
    )
    details: dict = Field(
        default_factory=dict,
        description="Engine-specific details and explanations",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Time taken by the engine to produce the score (ms)",
    )
    success: bool = Field(
        default=True,
        description="Whether the engine call succeeded",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if the engine call failed",
    )


class ScoringResult(BaseModel):
    """Aggregated scoring outcome for a single transaction.

    Contains per-engine scores, the weighted final score, the decision,
    and diagnostic metadata.
    """

    transaction_id: UUID = Field(
        ...,
        description="Transaction that was scored",
    )
    final_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Weighted aggregate fraud score",
    )
    rule_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score from the rule engine",
    )
    ml_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score from the ML model",
    )
    graph_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score from graph analysis",
    )
    historical_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score from historical velocity analysis",
    )
    decision: FraudDecision = Field(
        ...,
        description="Final fraud decision",
    )
    triggered_rules: list[str] = Field(
        default_factory=list,
        description="List of rule IDs that were triggered",
    )
    anomaly_flags: list[str] = Field(
        default_factory=list,
        description="Anomaly flags raised by ML scoring",
    )
    graph_patterns: list[str] = Field(
        default_factory=list,
        description="Suspicious graph patterns detected",
    )
    engine_results: list[EngineResult] = Field(
        default_factory=list,
        description="Raw results from each scoring engine",
    )
    scoring_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Total orchestration time in milliseconds",
    )
    scored_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when scoring completed",
    )

    @field_validator("decision", mode="before")
    @classmethod
    def _coerce_decision(cls, value: str | FraudDecision) -> FraudDecision:
        """Accept plain strings and coerce to the enum."""
        if isinstance(value, str):
            return FraudDecision(value.lower())
        return value
