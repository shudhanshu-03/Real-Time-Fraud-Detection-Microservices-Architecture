-- ============================================================================
-- Migration: 002_alerts.sql
-- Description: Alert management for the fraud detection platform
-- Author: Platform Engineering Team
-- Created: 2026-05-30
--
-- This migration creates the alerts table which stores fraud alerts generated
-- by the Rule Engine, ML Scoring Service, and Graph Analysis Service. Each
-- alert is linked to a specific transaction and carries individual component
-- scores along with triggered rule details and ML feature vectors.
--
-- Alert Lifecycle:
--   open → assigned → investigating → escalated → resolved → closed
--
-- Dependencies:
--   - 001_transactions.sql (transactions table)
--   - pgcrypto extension
-- ============================================================================

-- ==========================================================================
-- Table: alerts
-- ==========================================================================
-- Each alert represents a fraud detection event triggered by one or more
-- scoring components. Alerts flow through a defined lifecycle managed by
-- fraud analysts via the Case Management UI.
--
-- Scoring Breakdown:
--   - risk_score:  Composite score (weighted blend of all components)
--   - rule_score:  Score from the Rule Engine (deterministic rules)
--   - ml_score:    Score from the ML Scoring Service (model inference)
--   - graph_score: Score from the Graph Analysis Service (network patterns)
-- ==========================================================================
CREATE TABLE alerts (
    -- ── Identity ───────────────────────────────────────────────────────
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Transaction Link ───────────────────────────────────────────────
    transaction_id      UUID NOT NULL
                        REFERENCES transactions(id)
                        ON DELETE RESTRICT
                        ON UPDATE CASCADE,
    account_id          VARCHAR(255) NOT NULL,

    -- ── Scoring ────────────────────────────────────────────────────────
    risk_score          DECIMAL(5,4) NOT NULL CHECK (risk_score >= 0 AND risk_score <= 1),
    rule_score          DECIMAL(5,4) CHECK (rule_score >= 0 AND rule_score <= 1),
    ml_score            DECIMAL(5,4) CHECK (ml_score >= 0 AND ml_score <= 1),
    graph_score         DECIMAL(5,4) CHECK (graph_score >= 0 AND graph_score <= 1),

    -- ── Classification ─────────────────────────────────────────────────
    alert_type          VARCHAR(50) NOT NULL,     -- e.g., 'velocity', 'amount_anomaly', 'geo_anomaly', 'network_fraud'
    severity            VARCHAR(20) NOT NULL CHECK (
                            severity IN ('low', 'medium', 'high', 'critical')
                        ),
    category            VARCHAR(100),             -- e.g., 'card_not_present', 'account_takeover', 'synthetic_identity'

    -- ── Lifecycle ──────────────────────────────────────────────────────
    status              VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (
                            status IN ('open', 'assigned', 'investigating', 'escalated', 'resolved', 'closed')
                        ),
    assigned_to         UUID,                     -- FK to users table (created in a later migration)
    assigned_at         TIMESTAMPTZ,

    -- ── Resolution ─────────────────────────────────────────────────────
    resolution          VARCHAR(50) CHECK (
                            resolution IS NULL OR resolution IN (
                                'true_positive', 'false_positive',
                                'suspicious', 'insufficient_data',
                                'duplicate', 'auto_resolved'
                            )
                        ),
    resolution_notes    TEXT,
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID,                     -- FK to users table

    -- ── Scoring Details (JSONB for flexibility) ────────────────────────
    triggered_rules     JSONB DEFAULT '[]'::jsonb,
        -- Example: [{"rule_id": "VEL-001", "rule_name": "High Velocity", "score": 0.85, "details": {...}}]
    ml_features         JSONB DEFAULT '{}'::jsonb,
        -- Example: {"feature_vector": [...], "model_version": "v2.3.1", "confidence": 0.92}
    graph_patterns      JSONB DEFAULT '[]'::jsonb,
        -- Example: [{"pattern": "ring", "nodes": 5, "edges": 8, "centrality": 0.76}]

    -- ── SLA Tracking ───────────────────────────────────────────────────
    sla_deadline        TIMESTAMPTZ,
    sla_breached        BOOLEAN DEFAULT FALSE,

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes
-- ==========================================================================

-- Fast lookup of alerts by transaction (1:N relationship, typically 1:1)
CREATE INDEX idx_alert_transaction
    ON alerts(transaction_id);

-- Account-level alert history for analyst review and velocity analysis
CREATE INDEX idx_alert_account_time
    ON alerts(account_id, created_at DESC);

-- Operational dashboard: filter by status
CREATE INDEX idx_alert_status
    ON alerts(status)
    WHERE status NOT IN ('resolved', 'closed');

-- Severity-based prioritization for analyst queues
CREATE INDEX idx_alert_severity
    ON alerts(severity, created_at DESC);

-- Assignment tracking: find alerts assigned to a specific analyst
CREATE INDEX idx_alert_assigned
    ON alerts(assigned_to, status)
    WHERE assigned_to IS NOT NULL;

-- SLA monitoring: find alerts approaching or past deadline
CREATE INDEX idx_alert_sla
    ON alerts(sla_deadline)
    WHERE sla_breached = FALSE AND status NOT IN ('resolved', 'closed');

-- High-risk alert triage: quickly find critical/high severity open alerts
CREATE INDEX idx_alert_triage
    ON alerts(risk_score DESC, created_at ASC)
    WHERE status = 'open' AND severity IN ('high', 'critical');

-- Category-based analysis and reporting
CREATE INDEX idx_alert_category
    ON alerts(category, created_at DESC);

-- Resolution reporting (analyst performance, false positive rates)
CREATE INDEX idx_alert_resolution
    ON alerts(resolution, resolved_at DESC)
    WHERE resolution IS NOT NULL;

-- GIN indexes on JSONB columns for flexible querying
CREATE INDEX idx_alert_triggered_rules
    ON alerts USING GIN(triggered_rules);

CREATE INDEX idx_alert_ml_features
    ON alerts USING GIN(ml_features);

CREATE INDEX idx_alert_graph_patterns
    ON alerts USING GIN(graph_patterns);

-- Timestamp-based queries for reporting and analytics
CREATE INDEX idx_alert_created
    ON alerts(created_at DESC);

-- ==========================================================================
-- Trigger: auto-update updated_at on row modification
-- ==========================================================================
CREATE OR REPLACE FUNCTION update_alerts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_alerts_updated_at
    BEFORE UPDATE ON alerts
    FOR EACH ROW
    EXECUTE FUNCTION update_alerts_updated_at();

-- ==========================================================================
-- Comments
-- ==========================================================================
COMMENT ON TABLE alerts IS
    'Fraud alerts generated by scoring components (Rule Engine, ML, Graph Analysis). '
    'Each alert is linked to a transaction and progresses through a defined lifecycle.';

COMMENT ON COLUMN alerts.risk_score IS
    'Composite fraud risk score (0.0000–1.0000). Weighted blend of rule_score, ml_score, and graph_score.';

COMMENT ON COLUMN alerts.alert_type IS
    'Classification of the alert trigger. Common values: velocity, amount_anomaly, '
    'geo_anomaly, network_fraud, device_anomaly, behavioral_deviation.';

COMMENT ON COLUMN alerts.severity IS
    'Alert severity level. Determines SLA targets and routing priority. '
    'critical: 15 min SLA, high: 1 hr, medium: 4 hr, low: 24 hr.';

COMMENT ON COLUMN alerts.triggered_rules IS
    'JSONB array of rules that fired for this alert. Each entry contains '
    'rule_id, rule_name, individual score, and contextual details.';

COMMENT ON COLUMN alerts.ml_features IS
    'JSONB object containing the ML feature vector, model version, confidence interval, '
    'and SHAP/feature importance values for explainability.';

COMMENT ON COLUMN alerts.graph_patterns IS
    'JSONB array of suspicious graph patterns detected. Includes pattern type '
    '(ring, star, chain), node/edge counts, and centrality metrics.';

COMMENT ON COLUMN alerts.sla_deadline IS
    'Deadline by which this alert must be resolved. Computed based on severity level '
    'at alert creation time. Monitored by the SLA watchdog service.';
