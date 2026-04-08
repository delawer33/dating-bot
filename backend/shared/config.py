from pydantic_settings import BaseSettings, SettingsConfigDict


class SharedConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    app_env: str = "dev"

    @property
    def is_production(self) -> bool:
        return self.app_env == "prod"
