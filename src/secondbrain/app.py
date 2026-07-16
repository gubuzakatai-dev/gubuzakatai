import logging

from telegram import Update
from telegram.ext import Application

from secondbrain.bot.handlers import register_capture_handlers
from secondbrain.config.settings import Settings, load_settings
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository
from secondbrain.services.capture import CaptureService


def build_application(settings: Settings, capture_service: CaptureService | None = None) -> Application:
    """Build the Telegram application without starting network operations."""
    application = Application.builder().token(settings.telegram_bot_token).build()
    if capture_service is not None:
        register_capture_handlers(
            application,
            allowed_user_id=settings.telegram_allowed_user_id,
            capture_service=capture_service,
        )
    return application


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
    capture_service = CaptureService(CaptureRepository(engine))
    application = build_application(settings, capture_service)
    logging.getLogger(__name__).info("SecondBrain запускает Telegram polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
