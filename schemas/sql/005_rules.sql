CREATE TABLE rules (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_name           VARCHAR(255) NOT NULL,
    description         TEXT,
    category            VARCHAR(50) NOT NULL,           -- amount, velocity, geo, blocklist
    severity            VARCHAR(20) NOT NULL,           -- LOW, MEDIUM, HIGH, CRITICAL
    score_contribution  DECIMAL(5,4) NOT NULL,          -- 0.0000 to 1.0000
    
    -- The rule logic in JSON format.
    -- Example: {"field": "amount", "operator": ">", "value": 10000}
    -- Velocity example: {"type": "velocity", "entity": "card_number", "window": "24h", "limit": 5}
    conditions          JSONB NOT NULL,
    
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_rules_active ON rules(is_active);
CREATE INDEX idx_rules_category ON rules(category);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_rules_modtime
BEFORE UPDATE ON rules
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

-- Seed Initial Rules

-- 1. High Amount Transaction
INSERT INTO rules (rule_name, description, category, severity, score_contribution, conditions)
VALUES (
    'HIGH_AMOUNT_TXN',
    'Transaction amount is greater than $10,000',
    'amount',
    'HIGH',
    0.6000,
    '{"type": "condition", "field": "amount", "operator": ">", "value": 10000}'
);

-- 2. Cross-Border Mismatch (Billing Country != Shipping Country)
INSERT INTO rules (rule_name, description, category, severity, score_contribution, conditions)
VALUES (
    'CROSS_BORDER_MISMATCH',
    'Billing country does not match shipping country',
    'geo',
    'MEDIUM',
    0.4000,
    '{"type": "condition", "field": "billing_country", "operator": "!=", "value_field": "shipping_country"}'
);

-- 3. High Velocity 24H (More than 5 transactions in 24 hours on the same card)
INSERT INTO rules (rule_name, description, category, severity, score_contribution, conditions)
VALUES (
    'HIGH_VELOCITY_24H',
    'More than 5 transactions on the same card within 24 hours',
    'velocity',
    'CRITICAL',
    0.9000,
    '{"type": "velocity", "entity": "card_number", "window_seconds": 86400, "limit": 5}'
);
