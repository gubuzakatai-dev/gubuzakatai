import logging

from telegram import Update
from telegram.ext import Application

from secondbrain.config.settings import Settings, load_settings


def build_application(settings: Settings) -> Application:
    """Build the Telegram application without starting network operations."""
    return Application.builder().token(settings.telegram_bot_token).build()


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )


def main() -> None:
    configure_logging()
    settings = load_settings()
    application = build_application(settings)
    logging.getLogger(__name__).info("SecondBrain запускает Telegram polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
