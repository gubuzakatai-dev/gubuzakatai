import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str
    telegram_allowed_user_id: int


def load_settings() -> Settings:
    """Load and validate required settings from the local environment."""
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()

    if not token:
        raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN в .env")
    if not allowed_user_id:
        raise RuntimeError("Не задан TELEGRAM_ALLOWED_USER_ID в .env")

    try:
        parsed_user_id = int(allowed_user_id)
    except ValueError as error:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_ID должен быть целым числом") from error
    if parsed_user_id <= 0:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_ID должен быть положительным числом")

    return Settings(
        telegram_bot_token=token,
        telegram_allowed_user_id=parsed_user_id,
    )
