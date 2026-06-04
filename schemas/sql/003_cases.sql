-- ============================================================================
-- Migration: 003_cases.sql
-- Description: Case management system for fraud investigation workflows
-- Author: Platform Engineering Team
-- Created: 2026-05-30
--
-- This migration creates the case management schema consisting of four tables:
--   1. cases         – Master case record for fraud investigations
--   2. case_alerts   – Many-to-many link between cases and alerts
--   3. case_notes    – Analyst notes and commentary on cases
--   4. case_evidence – File attachments and evidence artifacts
--
-- Case Lifecycle:
--   open → assigned → investigating → escalated → resolved → closed
--
-- Case Number Format: CASE-YYYY-NNNNNN (e.g., CASE-2026-000142)
--
-- Dependencies:
--   - 001_transactions.sql (transactions table)
--   - 002_alerts.sql (alerts table)
--   - pgcrypto extension
-- ============================================================================


-- ==========================================================================
-- Sequence for case_number generation
-- ==========================================================================
-- Generates the numeric portion of case numbers (NNNNNN).
-- Resets annually via application logic or a scheduled job.
CREATE SEQUENCE IF NOT EXISTS case_number_seq
    START WITH 1
    INCREMENT BY 1
    NO MAXVALUE
    CACHE 10;


-- ==========================================================================
-- Table 1: cases
-- ==========================================================================
-- Master table for fraud investigation cases. A case groups one or more
-- related alerts into a single investigation workflow, enabling analysts
-- to track, collaborate, and resolve complex fraud scenarios.
-- ==========================================================================
CREATE TABLE cases (
    -- ── Identity ───────────────────────────────────────────────────────
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number         VARCHAR(20) UNIQUE NOT NULL
                        DEFAULT ('CASE-' || TO_CHAR(NOW(), 'YYYY') || '-' ||
                                 LPAD(nextval('case_number_seq')::TEXT, 6, '0')),

    -- ── Description ────────────────────────────────────────────────────
    title               VARCHAR(500) NOT NULL,
    description         TEXT,

    -- ── Classification ─────────────────────────────────────────────────
    case_type           VARCHAR(50) NOT NULL CHECK (
                            case_type IN (
                                'card_fraud', 'account_takeover', 'identity_theft',
                                'money_laundering', 'synthetic_identity', 'merchant_fraud',
                                'insider_threat', 'cyber_fraud', 'other'
                            )
                        ),
    priority            VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (
                            priority IN ('low', 'medium', 'high', 'critical')
                        ),

    -- ── Lifecycle ──────────────────────────────────────────────────────
    status              VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (
                            status IN ('open', 'assigned', 'investigating', 'escalated', 'resolved', 'closed')
                        ),
    assigned_to         UUID,                     -- FK to users table (created in later migration)
    assigned_at         TIMESTAMPTZ,
    team_id             UUID,                     -- FK to teams table (created in later migration)

    -- ── Financial Summary ──────────────────────────────────────────────
    total_amount        DECIMAL(18,4) DEFAULT 0,  -- Sum of transaction amounts in this case
    currency            VARCHAR(3),
    accounts_involved   INTEGER DEFAULT 0,        -- Count of unique accounts linked to this case

    -- ── Resolution ─────────────────────────────────────────────────────
    resolution          VARCHAR(50) CHECK (
                            resolution IS NULL OR resolution IN (
                                'confirmed_fraud', 'not_fraud', 'suspicious_activity',
                                'insufficient_evidence', 'referred_to_law_enforcement',
                                'account_action_taken', 'duplicate', 'auto_closed'
                            )
                        ),
    resolution_notes    TEXT,
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID,                     -- FK to users table

    -- ── SLA Tracking ───────────────────────────────────────────────────
    sla_deadline        TIMESTAMPTZ,
    sla_breached        BOOLEAN DEFAULT FALSE,

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes: cases
-- ==========================================================================

-- Case number lookup (unique index already created by UNIQUE constraint)
-- Additional index for pattern-based searches (LIKE 'CASE-2026-%')
CREATE INDEX idx_case_number_pattern
    ON cases(case_number varchar_pattern_ops);

-- Operational dashboard: filter by status
CREATE INDEX idx_case_status
    ON cases(status)
    WHERE status NOT IN ('resolved', 'closed');

-- Priority-based queue ordering
CREATE INDEX idx_case_priority_status
    ON cases(priority, status, created_at ASC);

-- Analyst workload: cases assigned to a specific analyst
CREATE INDEX idx_case_assigned
    ON cases(assigned_to, status)
    WHERE assigned_to IS NOT NULL;

-- Team workload distribution
CREATE INDEX idx_case_team
    ON cases(team_id, status)
    WHERE team_id IS NOT NULL;

-- Case type reporting and analytics
CREATE INDEX idx_case_type
    ON cases(case_type, created_at DESC);

-- SLA monitoring
CREATE INDEX idx_case_sla
    ON cases(sla_deadline)
    WHERE sla_breached = FALSE AND status NOT IN ('resolved', 'closed');

-- Resolution reporting
CREATE INDEX idx_case_resolution
    ON cases(resolution, resolved_at DESC)
    WHERE resolution IS NOT NULL;

-- Chronological listing
CREATE INDEX idx_case_created
    ON cases(created_at DESC);

-- Financial impact analysis: find high-value cases
CREATE INDEX idx_case_amount
    ON cases(total_amount DESC)
    WHERE total_amount > 0;


-- ==========================================================================
-- Trigger: auto-update updated_at on cases modification
-- ==========================================================================
CREATE OR REPLACE FUNCTION update_cases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_cases_updated_at
    BEFORE UPDATE ON cases
    FOR EACH ROW
    EXECUTE FUNCTION update_cases_updated_at();


-- ==========================================================================
-- Table 2: case_alerts
-- ==========================================================================
-- Junction table linking cases to alerts (many-to-many). An alert may be
-- linked to multiple cases (e.g., related investigations), and a case
-- always contains one or more alerts.
-- ==========================================================================
CREATE TABLE case_alerts (
    case_id             UUID NOT NULL
                        REFERENCES cases(id)
                        ON DELETE CASCADE
                        ON UPDATE CASCADE,
    alert_id            UUID NOT NULL
                        REFERENCES alerts(id)
                        ON DELETE RESTRICT
                        ON UPDATE CASCADE,

    -- ── Link Metadata ──────────────────────────────────────────────────
    linked_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    linked_by           UUID,                     -- FK to users table

    -- ── Composite Primary Key ──────────────────────────────────────────
    PRIMARY KEY (case_id, alert_id)
);

-- ==========================================================================
-- Indexes: case_alerts
-- ==========================================================================

-- Reverse lookup: find all cases containing a specific alert
CREATE INDEX idx_case_alerts_alert
    ON case_alerts(alert_id);

-- Find recently linked alerts (audit trail)
CREATE INDEX idx_case_alerts_linked
    ON case_alerts(linked_at DESC);

-- Analyst activity: who linked which alerts
CREATE INDEX idx_case_alerts_linked_by
    ON case_alerts(linked_by)
    WHERE linked_by IS NOT NULL;


-- ==========================================================================
-- Table 3: case_notes
-- ==========================================================================
-- Analyst notes, comments, and observations attached to a case. Supports
-- both internal notes (visible only to investigators) and external notes
-- (may be included in regulatory reports or shared with stakeholders).
-- ==========================================================================
CREATE TABLE case_notes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL
                        REFERENCES cases(id)
                        ON DELETE CASCADE
                        ON UPDATE CASCADE,

    -- ── Author ─────────────────────────────────────────────────────────
    author_id           UUID NOT NULL,            -- FK to users table

    -- ── Content ────────────────────────────────────────────────────────
    content             TEXT NOT NULL,
    note_type           VARCHAR(50) NOT NULL DEFAULT 'general' CHECK (
                            note_type IN (
                                'general', 'investigation', 'escalation',
                                'resolution', 'system', 'regulatory'
                            )
                        ),
    is_internal         BOOLEAN NOT NULL DEFAULT TRUE,

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes: case_notes
-- ==========================================================================

-- All notes for a case, chronologically ordered
CREATE INDEX idx_case_notes_case
    ON case_notes(case_id, created_at DESC);

-- Notes by author (analyst activity tracking)
CREATE INDEX idx_case_notes_author
    ON case_notes(author_id, created_at DESC);

-- Filter by note type (e.g., only escalation notes)
CREATE INDEX idx_case_notes_type
    ON case_notes(note_type, created_at DESC);

-- External-only notes for regulatory reports
CREATE INDEX idx_case_notes_external
    ON case_notes(case_id, created_at DESC)
    WHERE is_internal = FALSE;


-- ==========================================================================
-- Table 4: case_evidence
-- ==========================================================================
-- File attachments and evidence artifacts associated with a case.
-- Actual file storage is in object storage (S3/GCS); this table stores
-- metadata and references. Files include screenshots, documents, logs,
-- exported data, and any supporting evidence for the investigation.
-- ==========================================================================
CREATE TABLE case_evidence (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id             UUID NOT NULL
                        REFERENCES cases(id)
                        ON DELETE CASCADE
                        ON UPDATE CASCADE,

    -- ── File Metadata ──────────────────────────────────────────────────
    file_name           VARCHAR(500) NOT NULL,
    file_path           VARCHAR(1000) NOT NULL,   -- Object storage path (s3://bucket/path)
    file_type           VARCHAR(100) NOT NULL,     -- MIME type (e.g., 'application/pdf', 'image/png')
    file_size           BIGINT NOT NULL CHECK (file_size > 0),  -- Size in bytes

    -- ── Upload Metadata ────────────────────────────────────────────────
    uploaded_by         UUID NOT NULL,            -- FK to users table
    description         TEXT,

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes: case_evidence
-- ==========================================================================

-- All evidence for a case
CREATE INDEX idx_case_evidence_case
    ON case_evidence(case_id, created_at DESC);

-- Evidence uploaded by a specific user
CREATE INDEX idx_case_evidence_uploader
    ON case_evidence(uploaded_by, created_at DESC);

-- Filter by file type (e.g., find all PDF documents)
CREATE INDEX idx_case_evidence_type
    ON case_evidence(file_type);

-- Chronological evidence listing
CREATE INDEX idx_case_evidence_created
    ON case_evidence(created_at DESC);


-- ==========================================================================
-- Comments
-- ==========================================================================
COMMENT ON TABLE cases IS
    'Master case table for fraud investigations. Groups related alerts into '
    'a single investigation workflow with assignment, SLA tracking, and resolution.';

COMMENT ON COLUMN cases.case_number IS
    'Human-readable case identifier in format CASE-YYYY-NNNNNN. '
    'Auto-generated from case_number_seq sequence.';

COMMENT ON COLUMN cases.total_amount IS
    'Aggregate sum of all transaction amounts linked to this case. '
    'Updated by application logic when alerts are linked/unlinked.';

COMMENT ON COLUMN cases.accounts_involved IS
    'Count of unique account_ids across all alerts in this case. '
    'Helps gauge the scope and complexity of the investigation.';

COMMENT ON TABLE case_alerts IS
    'Junction table linking cases to alerts (many-to-many). Enables grouping '
    'multiple related alerts into a single investigation.';

COMMENT ON TABLE case_notes IS
    'Analyst notes and commentary on fraud cases. Supports internal notes '
    '(investigation-only) and external notes (for regulatory/compliance reports).';

COMMENT ON COLUMN case_notes.is_internal IS
    'When TRUE, note is only visible to investigators. When FALSE, note may '
    'be included in regulatory reports and external communications.';

COMMENT ON TABLE case_evidence IS
    'File attachments and evidence artifacts for fraud cases. Stores metadata '
    'only; actual files reside in object storage (S3/GCS).';

COMMENT ON COLUMN case_evidence.file_path IS
    'Full object storage path to the evidence file (e.g., s3://fraud-evidence/cases/CASE-2026-000142/doc.pdf).';
