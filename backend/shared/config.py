from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    rabbitmq_url: str = Field(
        default="amqp://guest:guest@localhost:5672//",
        description="AMQP URL for aio-pika and Celery broker",
    )
    app_env: str = "dev"
    registration_min_photos: int = 1
    registration_max_photos: int = 6
    preferences_max_distance_km: int = Field(default=500, ge=1, le=50_000)
    profile_bio_max_length: int = Field(default=900, ge=1, le=4000)
    profile_max_interests: int = Field(default=12, ge=1, le=50)
    # Optional: used for referral invite links (https://t.me/<username>?start=<code>)
    telegram_bot_username: str | None = Field(default=None, description="Bot @username without @")

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"
