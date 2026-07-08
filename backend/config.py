"""LiveBoard configuration — loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings pulled from env vars / .env file."""

    DATABASE_URL: str = "postgresql+asyncpg://liveboard:liveboard123@localhost/liveboard"
    REDIS_URL: str = "redis://localhost:6379"
    FRONTEND_URL: str = "http://localhost:5173"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
