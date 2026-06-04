"""
Shared domain models for the Fraud Detection Platform.

Defines Pydantic schemas used across all microservices for consistent
serialisation, validation, and API contracts.  Models are organised into
logical groups:

- **Enums** — status/decision enumerations shared across services.
- **Transactions** — base, creation, and response schemas for financial
  transactions.
- **Fraud Scoring** — result payload produced by the scoring engine.
- **Alerts & Cases** — investigation workflow entities.
- **Generic Responses** — standardised health, error, and pagination
  wrappers.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FraudDecision(str, Enum):
    """Possible outcomes of the fraud scoring pipeline."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    REVIEW = "review"


class AlertSeverity(str, Enum):
    """Severity levels for fraud alerts."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Lifecycle states for fraud alerts."""

    OPEN = "open"
    ASSIGNED = "assigned"
    INVESTIGATING = "investigating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class CaseStatus(str, Enum):
    """Lifecycle states for fraud investigation cases."""

    OPEN = "open"
    ASSIGNED = "assigned"
    INVESTIGATING = "investigating"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"


class Channel(str, Enum):
    """Notification delivery channels."""

    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"
    PUSH = "push"
    SLACK = "slack"


# ---------------------------------------------------------------------------
# Generic Response Models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Standardised health-check response.

    Attributes:
        status: Overall health status (e.g. ``"healthy"``, ``"degraded"``).
        service: Name of the reporting service.
        version: Semantic version of the reporting service.
        timestamp: ISO-8601 timestamp of the health check.
        dependencies: Per-dependency health status mapping.
    """

    status: str = Field(..., description="Overall health status.")
    service: str = Field(..., description="Name of the reporting service.")
    version: str = Field(..., description="Semantic version of the service.")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of the health check.",
    )
    dependencies: Dict[str, str] = Field(
        default_factory=dict,
        description="Per-dependency health status mapping.",
    )


class ErrorResponse(BaseModel):
    """Standardised error response returned by all API endpoints.

    Attributes:
        error_code: Machine-readable error code (e.g. ``"VALIDATION_ERROR"``).
        message: Human-readable description of the error.
        details: Optional structured details about the error.
        correlation_id: Request correlation ID for distributed tracing.
        timestamp: ISO-8601 timestamp of the error occurrence.
    """

    error_code: str = Field(..., description="Machine-readable error code.")
    message: str = Field(..., description="Human-readable error description.")
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional structured error details.",
    )
    correlation_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Request correlation ID for distributed tracing.",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of the error occurrence.",
    )


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper.

    Attributes:
        items: List of items on the current page.
        total: Total number of items across all pages.
        page: Current page number (1-indexed).
        page_size: Number of items per page.
        total_pages: Total number of pages.
    """

    items: List[T] = Field(..., description="Items on the current page.")
    total: int = Field(..., ge=0, description="Total number of items.")
    page: int = Field(..., ge=1, description="Current page number (1-indexed).")
    page_size: int = Field(..., ge=1, description="Number of items per page.")
    total_pages: int = Field(..., ge=0, description="Total number of pages.")


# ---------------------------------------------------------------------------
# Transaction Models
# ---------------------------------------------------------------------------


class TransactionBase(BaseModel):
    """Core transaction fields shared by create and response schemas.

    Attributes:
        transaction_id: Globally unique transaction identifier.
        card_number: Masked or tokenised card number.
        merchant_id: Unique identifier of the merchant.
        merchant_name: Human-readable merchant name.
        merchant_category: Merchant Category Code (MCC) or description.
        amount: Transaction amount in the specified currency.
        currency: ISO-4217 currency code (e.g. ``"USD"``).
        timestamp: Time the transaction was initiated.
        channel: Origination channel (e.g. ``"online"``, ``"pos"``).
        ip_address: IP address of the cardholder device, if available.
        device_id: Unique device identifier, if available.
        device_fingerprint: Browser or device fingerprint hash.
        location_lat: Latitude of the transaction location.
        location_lon: Longitude of the transaction location.
        billing_country: ISO-3166 country code of the billing address.
        shipping_country: ISO-3166 country code of the shipping address.
        is_recurring: Whether the transaction is part of a recurring series.
        is_international: Whether the transaction crosses borders.
        metadata: Arbitrary key-value metadata attached to the transaction.
    """

    transaction_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Globally unique transaction identifier.",
    )
    card_number: str = Field(
        ...,
        min_length=4,
        description="Masked or tokenised card number.",
    )
    merchant_id: str = Field(..., description="Unique merchant identifier.")
    merchant_name: str = Field(..., description="Human-readable merchant name.")
    merchant_category: str = Field(
        ...,
        description="Merchant Category Code (MCC) or description.",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount in the specified currency.",
    )
    currency: str = Field(
        default="USD",
        min_length=3,
        max_length=3,
        description="ISO-4217 currency code.",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Time the transaction was initiated.",
    )
    channel: str = Field(
        default="online",
        description="Origination channel (e.g. 'online', 'pos').",
    )
    ip_address: Optional[str] = Field(
        default=None,
        description="IP address of the cardholder device.",
    )
    device_id: Optional[str] = Field(
        default=None,
        description="Unique device identifier.",
    )
    device_fingerprint: Optional[str] = Field(
        default=None,
        description="Browser or device fingerprint hash.",
    )
    location_lat: Optional[float] = Field(
        default=None,
        ge=-90,
        le=90,
        description="Latitude of the transaction location.",
    )
    location_lon: Optional[float] = Field(
        default=None,
        ge=-180,
        le=180,
        description="Longitude of the transaction location.",
    )
    billing_country: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=3,
        description="ISO-3166 billing country code.",
    )
    shipping_country: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=3,
        description="ISO-3166 shipping country code.",
    )
    is_recurring: bool = Field(
        default=False,
        description="Whether the transaction is recurring.",
    )
    is_international: bool = Field(
        default=False,
        description="Whether the transaction crosses borders.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary key-value metadata.",
    )


class TransactionCreate(TransactionBase):
    """Schema for creating a new transaction.

    Inherits all fields from :class:`TransactionBase` with no additional
    modifications — exists to provide semantic clarity in API signatures.
    """

    pass


class TransactionResponse(TransactionBase):
    """Enriched transaction schema returned after processing.

    Extends :class:`TransactionBase` with server-assigned fields populated
    during ingestion and scoring.

    Attributes:
        id: Server-assigned primary key (UUID).
        risk_score: Composite fraud risk score (0.0 – 1.0).
        fraud_decision: Outcome from the fraud decision engine.
        created_at: Timestamp when the record was persisted.
        updated_at: Timestamp of the last update to the record.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Server-assigned primary key (UUID).",
    )
    risk_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Composite fraud risk score (0.0 – 1.0).",
    )
    fraud_decision: FraudDecision = Field(
        default=FraudDecision.PENDING,
        description="Outcome from the fraud decision engine.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the record was persisted.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the last update to the record.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Fraud Scoring Models
# ---------------------------------------------------------------------------


class FraudScoreResult(BaseModel):
    """Composite fraud scoring result produced by the scoring engine.

    Encapsulates individual sub-scores, the final blended score, and all
    signals that contributed to the decision.

    Attributes:
        transaction_id: ID of the scored transaction.
        final_score: Blended fraud risk score (0.0 – 1.0).
        rule_score: Score contribution from deterministic rules.
        ml_score: Score contribution from ML models.
        graph_score: Score contribution from graph analysis.
        historical_score: Score contribution from historical patterns.
        decision: Resulting fraud decision.
        triggered_rules: List of rule identifiers that fired.
        anomaly_flags: List of anomaly indicators detected.
        graph_patterns: List of suspicious graph patterns found.
        scoring_time_ms: Wall-clock time spent scoring (milliseconds).
    """

    transaction_id: str = Field(
        ...,
        description="ID of the scored transaction.",
    )
    final_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Blended fraud risk score (0.0 – 1.0).",
    )
    rule_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score contribution from deterministic rules.",
    )
    ml_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score contribution from ML models.",
    )
    graph_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score contribution from graph analysis.",
    )
    historical_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Score contribution from historical patterns.",
    )
    decision: FraudDecision = Field(
        ...,
        description="Resulting fraud decision.",
    )
    triggered_rules: List[str] = Field(
        default_factory=list,
        description="List of rule identifiers that fired.",
    )
    anomaly_flags: List[str] = Field(
        default_factory=list,
        description="List of anomaly indicators detected.",
    )
    graph_patterns: List[str] = Field(
        default_factory=list,
        description="List of suspicious graph patterns found.",
    )
    scoring_time_ms: float = Field(
        ...,
        ge=0,
        description="Wall-clock scoring time in milliseconds.",
    )


# ---------------------------------------------------------------------------
# Alert Models
# ---------------------------------------------------------------------------


class AlertBase(BaseModel):
    """Core alert fields shared by create and response schemas.

    Attributes:
        transaction_id: ID of the transaction that triggered the alert.
        severity: Alert severity level.
        title: Short, descriptive title for the alert.
        description: Detailed description of the suspicious activity.
        rule_ids: List of rule IDs that triggered this alert.
        score: Fraud risk score at the time of alert creation.
        metadata: Arbitrary key-value metadata for the alert.
    """

    transaction_id: str = Field(
        ...,
        description="ID of the transaction that triggered the alert.",
    )
    severity: AlertSeverity = Field(
        ...,
        description="Alert severity level.",
    )
    title: str = Field(
        ...,
        max_length=256,
        description="Short, descriptive title for the alert.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed description of the suspicious activity.",
    )
    rule_ids: List[str] = Field(
        default_factory=list,
        description="List of rule IDs that triggered this alert.",
    )
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraud risk score at the time of alert creation.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary key-value metadata.",
    )


class AlertCreate(AlertBase):
    """Schema for creating a new fraud alert.

    Inherits all fields from :class:`AlertBase` — exists for semantic
    clarity in API signatures.
    """

    pass


class AlertResponse(AlertBase):
    """Enriched alert schema returned after persistence.

    Extends :class:`AlertBase` with server-assigned lifecycle fields.

    Attributes:
        id: Server-assigned primary key (UUID).
        status: Current alert lifecycle status.
        assigned_to: Analyst user ID assigned to the alert.
        created_at: Timestamp when the alert was created.
        updated_at: Timestamp of the last update.
        resolved_at: Timestamp when the alert was resolved.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Server-assigned primary key (UUID).",
    )
    status: AlertStatus = Field(
        default=AlertStatus.OPEN,
        description="Current alert lifecycle status.",
    )
    assigned_to: Optional[str] = Field(
        default=None,
        description="Analyst user ID assigned to the alert.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the alert was created.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the last update.",
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the alert was resolved.",
    )

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Case Models
# ---------------------------------------------------------------------------


class CaseBase(BaseModel):
    """Core investigation case fields.

    Attributes:
        title: Short, descriptive title for the case.
        description: Detailed description of the investigation.
        alert_ids: List of alert IDs associated with this case.
        priority: Case priority (reuses AlertSeverity for consistency).
        assigned_to: Analyst user ID assigned to the case.
        tags: Free-form tags for categorisation.
        metadata: Arbitrary key-value metadata for the case.
    """

    title: str = Field(
        ...,
        max_length=256,
        description="Short, descriptive title for the case.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Detailed description of the investigation.",
    )
    alert_ids: List[str] = Field(
        default_factory=list,
        description="List of alert IDs associated with this case.",
    )
    priority: AlertSeverity = Field(
        default=AlertSeverity.MEDIUM,
        description="Case priority level.",
    )
    assigned_to: Optional[str] = Field(
        default=None,
        description="Analyst user ID assigned to the case.",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Free-form tags for categorisation.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Arbitrary key-value metadata.",
    )


class CaseCreate(CaseBase):
    """Schema for creating a new investigation case.

    Inherits all fields from :class:`CaseBase` — exists for semantic
    clarity in API signatures.
    """

    pass


class CaseResponse(CaseBase):
    """Enriched case schema returned after persistence.

    Extends :class:`CaseBase` with server-assigned lifecycle fields.

    Attributes:
        id: Server-assigned primary key (UUID).
        status: Current case lifecycle status.
        created_at: Timestamp when the case was created.
        updated_at: Timestamp of the last update.
        resolved_at: Timestamp when the case was resolved.
        closed_at: Timestamp when the case was closed.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Server-assigned primary key (UUID).",
    )
    status: CaseStatus = Field(
        default=CaseStatus.OPEN,
        description="Current case lifecycle status.",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the case was created.",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of the last update.",
    )
    resolved_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the case was resolved.",
    )
    closed_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the case was closed.",
    )

    model_config = {"from_attributes": True}
