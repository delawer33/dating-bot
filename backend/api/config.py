from pydantic import Field

from shared.config import SharedConfig


class APIConfig(SharedConfig):

    bot_secret: str
    # Telegram Bot API token (getFile + file download) — same value as the bot.
    bot_token: str
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str = "us-east-1"
    telegram_file_max_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
    )

    google_maps_api_key: str | None = None
    nominatim_user_agent: str = "DatingBot/1.0"


settings = APIConfig()
