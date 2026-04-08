from shared.config import SharedConfig


class APIConfig(SharedConfig):

    bot_secret: str

    google_maps_api_key: str | None = None

    nominatim_user_agent: str = "DatingBot/1.0"


settings = APIConfig()
