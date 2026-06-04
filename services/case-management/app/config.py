from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "case-management"
    PG_USER: str = "fraud_user"
    PG_PASSWORD: str = "fraud_pass"
    PG_HOST: str = "postgres"
    PG_PORT: int = 5432
    PG_DB: str = "fraud_transactions"
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:29092"
    CASE_TOPIC: str = "case.opened"

    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.PG_USER}:{self.PG_PASSWORD}@{self.PG_HOST}:{self.PG_PORT}/{self.PG_DB}"


settings = Settings()
