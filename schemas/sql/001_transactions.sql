-- ============================================================================
-- Migration: 001_transactions.sql
-- Description: Core transaction storage for the fraud detection platform
-- Author: Platform Engineering Team
-- Created: 2026-05-30
--
-- This migration creates the primary transactions table which serves as the
-- central data store for all financial transactions flowing through the
-- fraud detection pipeline. Every transaction ingested via the Transaction
-- Ingestion Service lands here after initial validation and enrichment.
--
-- Dependencies:
--   - PostgreSQL 14+ (for gen_random_uuid, JSONB optimizations)
--   - pgcrypto extension
--
-- Estimated Table Size (Production):
--   - ~100M rows/day, ~3B rows/month with 90-day retention
--   - ~500 bytes/row average → ~1.5 TB/month uncompressed
-- ============================================================================

-- ==========================================================================
-- Extensions
-- ==========================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==========================================================================
-- Table: transactions
-- ==========================================================================
-- Core transaction record. Each row represents a single financial event
-- captured by the platform. Fields are grouped logically:
--   1. Identity & Classification
--   2. Financial Details
--   3. Cardholder / Account Information
--   4. Merchant Information
--   5. Device & Geolocation
--   6. Channel & Entry Mode
--   7. Enrichment & Scoring (populated by downstream services)
--   8. Timestamps & Lifecycle
--   9. Extensible Metadata
-- ==========================================================================
CREATE TABLE transactions (
    -- ── Identity & Classification ──────────────────────────────────────
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id         VARCHAR(255) UNIQUE NOT NULL,
    transaction_type    VARCHAR(50) NOT NULL CHECK (
                            transaction_type IN ('purchase', 'transfer', 'withdrawal', 'refund', 'payment')
                        ),

    -- ── Financial Details ──────────────────────────────────────────────
    amount              DECIMAL(18,4) NOT NULL CHECK (amount > 0),
    currency            VARCHAR(3) NOT NULL,

    -- ── Cardholder / Account ───────────────────────────────────────────
    account_id          VARCHAR(255) NOT NULL,
    card_hash           VARCHAR(64),          -- SHA-256 hash of full card number
    card_bin            VARCHAR(8),           -- Bank Identification Number (first 6-8 digits)
    card_last_four      VARCHAR(4),           -- Last four digits for display/reference

    -- ── Merchant ───────────────────────────────────────────────────────
    merchant_id         VARCHAR(255),
    merchant_name       VARCHAR(255),
    merchant_category   VARCHAR(10),          -- MCC (Merchant Category Code)
    merchant_country    VARCHAR(3),           -- ISO 3166-1 alpha-3

    -- ── Device & Location ──────────────────────────────────────────────
    device_id           VARCHAR(255),
    device_fingerprint  VARCHAR(255),         -- Browser/device fingerprint hash
    ip_address          INET,
    geo_latitude        DECIMAL(10,7),
    geo_longitude       DECIMAL(10,7),
    geo_country         VARCHAR(3),           -- ISO 3166-1 alpha-3
    geo_city            VARCHAR(100),

    -- ── Channel ────────────────────────────────────────────────────────
    channel             VARCHAR(50) CHECK (
                            channel IN ('online', 'pos', 'atm', 'mobile', 'phone')
                        ),
    entry_mode          VARCHAR(50) CHECK (
                            entry_mode IN ('chip', 'swipe', 'contactless', 'manual', 'token')
                        ),

    -- ── Enrichment (populated by scoring / ML pipeline) ────────────────
    is_international    BOOLEAN DEFAULT FALSE,
    risk_score          DECIMAL(5,4) CHECK (risk_score >= 0 AND risk_score <= 1),
    fraud_decision      VARCHAR(20) DEFAULT 'pending' CHECK (
                            fraud_decision IN ('pending', 'approved', 'declined', 'review')
                        ),

    -- ── Timestamps ─────────────────────────────────────────────────────
    transaction_time    TIMESTAMPTZ NOT NULL,  -- When the transaction actually occurred
    ingested_at         TIMESTAMPTZ DEFAULT NOW(),  -- When we received it
    processed_at        TIMESTAMPTZ,          -- When scoring completed

    -- ── Metadata ───────────────────────────────────────────────────────
    metadata            JSONB DEFAULT '{}'::jsonb
);

-- ==========================================================================
-- Indexes
-- ==========================================================================

-- Primary query pattern: look up transactions by account, ordered by time
CREATE INDEX idx_txn_account_time
    ON transactions(account_id, transaction_time DESC);

-- Card-level velocity checks and history
CREATE INDEX idx_txn_card_time
    ON transactions(card_hash, transaction_time DESC);

-- Merchant-level aggregation and analysis
CREATE INDEX idx_txn_merchant
    ON transactions(merchant_id);

-- Device-based fraud ring detection
CREATE INDEX idx_txn_device
    ON transactions(device_id);

-- IP-based velocity and geolocation checks
CREATE INDEX idx_txn_ip
    ON transactions(ip_address);

-- Filter by fraud decision status (operational dashboards)
CREATE INDEX idx_txn_decision
    ON transactions(fraud_decision);

-- Partial index: only high-risk transactions for alert generation
CREATE INDEX idx_txn_risk
    ON transactions(risk_score)
    WHERE risk_score > 0.7;

-- GIN index on JSONB metadata for flexible querying
CREATE INDEX idx_txn_metadata
    ON transactions USING GIN(metadata);

-- Ingestion time for replay, reprocessing, and audit trails
CREATE INDEX idx_txn_ingested
    ON transactions(ingested_at DESC);

-- ==========================================================================
-- PARTITIONING STRATEGY (Production)
-- ==========================================================================
--
-- In production, this table MUST be partitioned to handle the expected
-- volume of ~100M transactions/day. The recommended strategy is:
--
--   1. RANGE PARTITION by transaction_time (monthly partitions)
--      This aligns with the most common query pattern (time-bounded lookups)
--      and allows efficient partition pruning.
--
--      Example:
--        CREATE TABLE transactions (
--            ...
--        ) PARTITION BY RANGE (transaction_time);
--
--        CREATE TABLE transactions_2026_01 PARTITION OF transactions
--            FOR VALUES FROM ('2026-01-01') TO ('2026-02-01');
--        CREATE TABLE transactions_2026_02 PARTITION OF transactions
--            FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
--        -- etc.
--
--   2. SUB-PARTITIONING by account_id hash (optional, for very high volume)
--      If monthly partitions still exceed comfortable sizes (~500M+ rows),
--      consider hash sub-partitioning:
--
--        CREATE TABLE transactions (
--            ...
--        ) PARTITION BY RANGE (transaction_time);
--
--        CREATE TABLE transactions_2026_01 PARTITION OF transactions
--            FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
--            PARTITION BY HASH (account_id);
--
--        CREATE TABLE transactions_2026_01_p0
--            PARTITION OF transactions_2026_01
--            FOR VALUES WITH (MODULUS 8, REMAINDER 0);
--        -- ... repeat for remainders 1-7
--
--   3. RETENTION POLICY
--      - Hot data (0-30 days): Keep on fast NVMe storage
--      - Warm data (30-90 days): Move to standard SSD tablespace
--      - Cold data (90-365 days): Archive to columnar storage (e.g., Citus)
--      - Frozen data (365+ days): Export to object storage (S3/GCS) + drop partition
--
--      Automate with pg_partman:
--        SELECT partman.create_parent(
--            p_parent_table := 'public.transactions',
--            p_control := 'transaction_time',
--            p_type := 'range',
--            p_interval := '1 month',
--            p_premake := 3
--        );
--
--   4. PARTITION MAINTENANCE
--      - Use pg_partman for automatic partition creation and detachment
--      - Schedule VACUUM ANALYZE on individual partitions (not the parent)
--      - Monitor partition sizes via pg_stat_user_tables
--      - Set up alerts for partitions exceeding size thresholds
--
--   5. INDEX CONSIDERATIONS FOR PARTITIONED TABLES
--      - Indexes are created per-partition automatically when defined on parent
--      - Consider CONCURRENTLY index creation on large existing partitions
--      - Partial indexes (e.g., idx_txn_risk) are especially effective
--        on partitioned tables as they remain small per-partition
--
-- ==========================================================================
-- COMPRESSION NOTES (Production)
-- ==========================================================================
--
-- For TimescaleDB deployments, enable native compression on older chunks:
--
--   ALTER TABLE transactions SET (
--       timescaledb.compress,
--       timescaledb.compress_segmentby = 'account_id',
--       timescaledb.compress_orderby = 'transaction_time DESC'
--   );
--
--   SELECT add_compression_policy('transactions', INTERVAL '7 days');
--
-- Expected compression ratio: 10-15x for transaction data
--
-- ==========================================================================

-- Add table and column comments for documentation
COMMENT ON TABLE transactions IS
    'Core transaction table for the fraud detection platform. Stores all financial '
    'events with enrichment data populated by the scoring pipeline.';

COMMENT ON COLUMN transactions.external_id IS
    'Unique transaction identifier from the originating system (e.g., payment processor reference).';

COMMENT ON COLUMN transactions.card_hash IS
    'SHA-256 hash of the full card number. Used for card-level velocity checks without storing PAN.';

COMMENT ON COLUMN transactions.merchant_category IS
    'Merchant Category Code (MCC) - ISO 18245 standard classification.';

COMMENT ON COLUMN transactions.risk_score IS
    'Composite fraud risk score (0.0000 = safe, 1.0000 = certain fraud). '
    'Computed by the ML Scoring Service as a weighted blend of rule, ML, and graph scores.';

COMMENT ON COLUMN transactions.fraud_decision IS
    'Final fraud disposition: pending (awaiting scoring), approved (legitimate), '
    'declined (blocked), review (sent to analyst queue).';

COMMENT ON COLUMN transactions.metadata IS
    'Extensible JSONB field for additional context. May include: '
    'original_request, enrichment_data, 3ds_result, tokenization_info, etc.';
