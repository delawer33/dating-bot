from pydantic import model_validator

from shared.config import SharedConfig


class BotConfig(SharedConfig):

    bot_token: str

    bot_transport: str = "polling"

    webhook_url: str | None = None
    webhook_port: int = 8443

    webhook_secret_token: str | None = None

    redis_url: str

    api_base_url: str
    api_secret: str

    @model_validator(mode="after")
    def _check_webhook_config(self) -> "BotConfig":
        if self.bot_transport == "webhook" and not self.webhook_url:
            raise ValueError("WEBHOOK_URL is required when BOT_TRANSPORT=webhook")
        return self


settings = BotConfig()
