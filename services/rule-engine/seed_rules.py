import asyncio
import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://fraud_user:fraud_pass@localhost:5432/fraud_transactions")


async def seed_rules():
    print(f"Connecting to {DATABASE_URL}...")
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    rules = [
        {
            "id": "1001",
            "rule_name": "High Value Anomaly",
            "category": "AMOUNT",
            "severity": "HIGH",
            "score_contribution": 0.4,
            "conditions": json.dumps({"type": "condition", "field": "amount", "operator": ">", "value": 5000.0}),
        },
        {
            "id": "1002",
            "rule_name": "Extreme Value Anomaly",
            "category": "AMOUNT",
            "severity": "CRITICAL",
            "score_contribution": 0.8,
            "conditions": json.dumps({"type": "condition", "field": "amount", "operator": ">", "value": 15000.0}),
        },
        {
            "id": "1003",
            "rule_name": "High Velocity (Card)",
            "category": "VELOCITY",
            "severity": "HIGH",
            "score_contribution": 0.5,
            "conditions": json.dumps({"type": "velocity", "entity": "card_number", "window_seconds": 3600, "limit": 5}),
        },
        {
            "id": "1004",
            "rule_name": "High Risk MCC",
            "category": "MERCHANT",
            "severity": "MEDIUM",
            "score_contribution": 0.3,
            "conditions": json.dumps(
                {"type": "condition", "field": "merchant_id", "operator": "==", "value": "CRYPTO_EXCHANGE"}
            ),
        },
    ]

    async with async_session() as session:
        # Check if table exists
        await session.execute(
            text("""
            CREATE TABLE IF NOT EXISTS rules (
                id VARCHAR(255) PRIMARY KEY,
                rule_name VARCHAR(255) NOT NULL,
                category VARCHAR(255) NOT NULL,
                severity VARCHAR(255) NOT NULL,
                score_contribution FLOAT NOT NULL,
                conditions JSONB NOT NULL,
                is_active BOOLEAN DEFAULT true
            )
        """)
        )

        # Clear existing rules
        print("Clearing existing rules...")
        await session.execute(text("DELETE FROM rules"))

        # Insert new rules
        print("Inserting new rules...")
        for rule in rules:
            await session.execute(
                text("""
                INSERT INTO rules (id, rule_name, category, severity, score_contribution, conditions, is_active)
                VALUES (:id, :rule_name, :category, :severity, :score_contribution, :conditions, true)
                """),
                {
                    "id": rule["id"],
                    "rule_name": rule["rule_name"],
                    "category": rule["category"],
                    "severity": rule["severity"],
                    "score_contribution": rule["score_contribution"],
                    "conditions": rule["conditions"],
                },
            )

        await session.commit()
        print(f"Successfully seeded {len(rules)} rules.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_rules())
