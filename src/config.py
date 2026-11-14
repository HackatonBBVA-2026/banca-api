from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./banca.db"
    SEED_VALUE: int = 42
    SIMULATION_ENABLED: bool = True
    SIMULATION_INTERVAL_MIN: int = 10
    SIMULATION_INTERVAL_MAX: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
