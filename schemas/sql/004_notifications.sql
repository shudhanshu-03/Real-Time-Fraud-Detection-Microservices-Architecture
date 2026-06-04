-- ============================================================================
-- Migration: 004_notifications.sql
-- Description: Notification system for the fraud detection platform
-- Author: Platform Engineering Team
-- Created: 2026-05-30
--
-- This migration creates the notification subsystem consisting of two tables:
--   1. notifications             – Individual notification delivery records
--   2. notification_preferences  – Per-user, per-channel notification settings
--
-- The Notification Service consumes events from Kafka (alert.created,
-- case.escalated, sla.breached, etc.) and dispatches notifications across
-- multiple channels based on user preferences and alert routing rules.
--
-- Supported Channels: email, sms, webhook, push, slack
--
-- Dependencies:
--   - pgcrypto extension
-- ============================================================================


-- ==========================================================================
-- Table 1: notifications
-- ==========================================================================
-- Each row represents a single notification delivery attempt. The service
-- creates one notification record per channel per recipient. Failed
-- deliveries are retried up to a configurable maximum (default: 5).
--
-- Lifecycle:  pending → sent → delivered
--                 └──→ failed (retry) → sent → delivered
--                                  └──→ failed (exhausted)
-- ==========================================================================
CREATE TABLE notifications (
    -- ── Identity ───────────────────────────────────────────────────────
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── Recipient ──────────────────────────────────────────────────────
    user_id             UUID NOT NULL,            -- FK to users table (created in later migration)

    -- ── Channel & Type ─────────────────────────────────────────────────
    channel             VARCHAR(20) NOT NULL CHECK (
                            channel IN ('email', 'sms', 'webhook', 'push', 'slack')
                        ),
    notification_type   VARCHAR(50) NOT NULL,     -- e.g., 'alert_created', 'case_escalated', 'sla_warning', 'daily_digest'

    -- ── Content ────────────────────────────────────────────────────────
    subject             VARCHAR(500),             -- Subject line (email/push) or title (slack)
    content             TEXT NOT NULL,            -- Body content (HTML for email, plain text for SMS, JSON for webhook)
    metadata            JSONB DEFAULT '{}'::jsonb,
        -- Channel-specific metadata. Examples:
        --   email:   {"from": "alerts@fraud.platform", "cc": [...], "template_id": "..."}
        --   sms:     {"phone_number": "+1...", "provider": "twilio"}
        --   webhook: {"url": "https://...", "headers": {...}, "http_method": "POST"}
        --   push:    {"device_tokens": [...], "badge": 3, "sound": "alert"}
        --   slack:   {"channel": "#fraud-alerts", "thread_ts": "...", "blocks": [...]}

    -- ── Delivery Status ────────────────────────────────────────────────
    status              VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (
                            status IN ('pending', 'sent', 'delivered', 'failed')
                        ),
    sent_at             TIMESTAMPTZ,              -- When the notification was dispatched
    delivered_at        TIMESTAMPTZ,              -- When delivery confirmation was received
    failed_at           TIMESTAMPTZ,              -- When the last failure occurred
    error_message       TEXT,                     -- Last error message from delivery attempt
    retry_count         INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),

    -- ── Reference (polymorphic link to source entity) ──────────────────
    reference_type      VARCHAR(50),              -- e.g., 'alert', 'case', 'sla', 'system'
    reference_id        UUID,                     -- ID of the source entity (alert_id, case_id, etc.)

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================================
-- Indexes: notifications
-- ==========================================================================

-- User notification history (inbox view)
CREATE INDEX idx_notification_user_time
    ON notifications(user_id, created_at DESC);

-- User notifications by channel (channel-specific history)
CREATE INDEX idx_notification_user_channel
    ON notifications(user_id, channel, created_at DESC);

-- Delivery queue: find pending notifications for processing
CREATE INDEX idx_notification_pending
    ON notifications(status, created_at ASC)
    WHERE status = 'pending';

-- Failed notification retry queue
CREATE INDEX idx_notification_failed_retry
    ON notifications(status, retry_count, failed_at ASC)
    WHERE status = 'failed' AND retry_count < 5;

-- Channel-level delivery monitoring
CREATE INDEX idx_notification_channel_status
    ON notifications(channel, status, created_at DESC);

-- Notification type analytics
CREATE INDEX idx_notification_type
    ON notifications(notification_type, created_at DESC);

-- Reference lookup: find all notifications for a specific entity
CREATE INDEX idx_notification_reference
    ON notifications(reference_type, reference_id)
    WHERE reference_type IS NOT NULL;

-- GIN index on metadata for flexible querying
CREATE INDEX idx_notification_metadata
    ON notifications USING GIN(metadata);

-- Chronological listing
CREATE INDEX idx_notification_created
    ON notifications(created_at DESC);

-- Delivery timing analysis
CREATE INDEX idx_notification_sent
    ON notifications(sent_at DESC)
    WHERE sent_at IS NOT NULL;


-- ==========================================================================
-- Table 2: notification_preferences
-- ==========================================================================
-- Stores per-user, per-channel notification preferences. Users can enable
-- or disable specific channels and configure filters to control which
-- notification types they receive on each channel.
--
-- The Notification Service checks preferences before dispatching:
--   1. Is the channel enabled for this user?
--   2. Does the notification type pass the user's filters?
--   3. Are quiet hours in effect? (checked via filters.quiet_hours)
-- ==========================================================================
CREATE TABLE notification_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- ── User & Channel ─────────────────────────────────────────────────
    user_id             UUID NOT NULL,            -- FK to users table
    channel             VARCHAR(20) NOT NULL CHECK (
                            channel IN ('email', 'sms', 'webhook', 'push', 'slack')
                        ),

    -- ── Preferences ────────────────────────────────────────────────────
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    filters             JSONB DEFAULT '{}'::jsonb,
        -- Filter configuration. Example:
        -- {
        --     "min_severity": "high",
        --     "notification_types": ["alert_created", "case_escalated", "sla_breached"],
        --     "quiet_hours": {"start": "22:00", "end": "07:00", "timezone": "America/New_York"},
        --     "digest_mode": "hourly",
        --     "rate_limit": {"max_per_hour": 20}
        -- }

    -- ── Timestamps ─────────────────────────────────────────────────────
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ── Constraints ────────────────────────────────────────────────────
    CONSTRAINT uq_user_channel UNIQUE (user_id, channel)
);

-- ==========================================================================
-- Indexes: notification_preferences
-- ==========================================================================

-- Lookup preferences for a user (all channels)
CREATE INDEX idx_notif_pref_user
    ON notification_preferences(user_id);

-- Find all users with a specific channel enabled (for broadcast notifications)
CREATE INDEX idx_notif_pref_channel_enabled
    ON notification_preferences(channel, enabled)
    WHERE enabled = TRUE;

-- GIN index on filters for querying specific filter configurations
CREATE INDEX idx_notif_pref_filters
    ON notification_preferences USING GIN(filters);


-- ==========================================================================
-- Trigger: auto-update updated_at on notification_preferences modification
-- ==========================================================================
CREATE OR REPLACE FUNCTION update_notification_preferences_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notification_preferences_updated_at
    BEFORE UPDATE ON notification_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_notification_preferences_updated_at();


-- ==========================================================================
-- Seed: Default notification preference templates
-- ==========================================================================
-- These are applied by the application when a new user is created.
-- Stored here as documentation of the default configuration.
--
-- INSERT INTO notification_preferences (user_id, channel, enabled, filters)
-- VALUES
--     (:user_id, 'email', TRUE,  '{"min_severity": "low", "digest_mode": "realtime"}'::jsonb),
--     (:user_id, 'push',  TRUE,  '{"min_severity": "medium", "digest_mode": "realtime"}'::jsonb),
--     (:user_id, 'slack', TRUE,  '{"min_severity": "high", "notification_types": ["alert_created", "case_escalated", "sla_breached"]}'::jsonb),
--     (:user_id, 'sms',   FALSE, '{"min_severity": "critical"}'::jsonb),
--     (:user_id, 'webhook', FALSE, '{}'::jsonb);
--


-- ==========================================================================
-- Comments
-- ==========================================================================
COMMENT ON TABLE notifications IS
    'Individual notification delivery records. Each row represents a single '
    'notification sent to a user on a specific channel. Tracks delivery status, '
    'retry attempts, and links back to the source entity (alert, case, etc.).';

COMMENT ON COLUMN notifications.channel IS
    'Delivery channel: email (SMTP/SendGrid), sms (Twilio), webhook (HTTP POST), '
    'push (FCM/APNs), slack (Slack API).';

COMMENT ON COLUMN notifications.notification_type IS
    'Categorization of the notification. Common types: alert_created, alert_escalated, '
    'case_assigned, case_escalated, sla_warning, sla_breached, daily_digest, system_alert.';

COMMENT ON COLUMN notifications.metadata IS
    'Channel-specific delivery metadata (recipient details, template IDs, webhook URLs, etc.). '
    'Structure varies by channel.';

COMMENT ON COLUMN notifications.reference_type IS
    'Polymorphic reference type identifying the source entity. Values: alert, case, sla, system. '
    'Used with reference_id for cross-referencing.';

COMMENT ON COLUMN notifications.retry_count IS
    'Number of delivery retry attempts. Max retries configurable per channel (default: 5). '
    'Retry backoff: exponential with jitter.';

COMMENT ON TABLE notification_preferences IS
    'Per-user, per-channel notification preferences. Controls which notifications '
    'a user receives on each channel, including severity filters, quiet hours, '
    'digest mode, and rate limiting.';

COMMENT ON COLUMN notification_preferences.filters IS
    'JSONB filter configuration. Supports: min_severity, notification_types (allowlist), '
    'quiet_hours (start/end/timezone), digest_mode (realtime/hourly/daily), '
    'rate_limit (max_per_hour).';

COMMENT ON COLUMN notification_preferences.enabled IS
    'Master toggle for the channel. When FALSE, no notifications are sent '
    'on this channel regardless of filter settings.';
