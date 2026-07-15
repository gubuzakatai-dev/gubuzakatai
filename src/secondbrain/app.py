import logging

from telegram import Update
from telegram.ext import Application

from secondbrain.config.settings import Settings, load_settings
from secondbrain.storage.database import create_database_engine, initialize_database


def build_application(settings: Settings) -> Application:
    """Build the Telegram application without starting network operations."""
    return Application.builder().token(settings.telegram_bot_token).build()


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        level=logging.INFO,
    )
    # HTTPX logs Telegram request URLs, which contain the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    configure_logging()
    settings = load_settings()
    engine = create_database_engine(settings.database_path)
    initialize_database(engine)
    application = build_application(settings)
    logging.getLogger(__name__).info("SecondBrain запускает Telegram polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
