import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fraud_rules")

engine = None
AsyncSessionLocal = None


async def init_db():
    global engine, AsyncSessionLocal
    engine = create_async_engine(DATABASE_URL, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def close_db():
    global engine
    if engine:
        await engine.dispose()


async def get_db_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def fetch_active_rules():
    """Fetch all active rules from the database."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                "SELECT id, rule_name, category, severity, score_contribution, conditions FROM rules WHERE is_active = true"
            )
        )
        rules = []
        for row in result:
            rules.append(
                {
                    "id": str(row[0]),
                    "rule_name": row[1],
                    "category": row[2],
                    "severity": row[3],
                    "score_contribution": float(row[4]),
                    "conditions": row[5],
                }
            )
        return rules
