import logging

from telegram import Update
from telegram.ext import Application, ContextTypes

from secondbrain.bot.handlers import register_capture_handlers
from secondbrain.config.settings import Settings, load_settings
from secondbrain.services.capture import CaptureService
from secondbrain.services.link_metadata import LinkMetadataService
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, LinkMetadataRepository

LINK_METADATA_JOB_NAME = "link_metadata"
LINK_METADATA_INTERVAL_SECONDS = 60


def build_application(
    settings: Settings,
    capture_service: CaptureService | None = None,
    link_metadata_service: LinkMetadataService | None = None,
) -> Application:
    """Build the Telegram application without starting network operations."""
    application = Application.builder().token(settings.telegram_bot_token).build()
    if capture_service is not None:
        register_capture_handlers(
            application,
            allowed_user_id=settings.telegram_allowed_user_id,
            capture_service=capture_service,
        )
    if link_metadata_service is not None:
        register_link_metadata_job(application, link_metadata_service)
    return application


def register_link_metadata_job(application: Application, service: LinkMetadataService) -> None:
    async def process_link_metadata(_context: ContextTypes.DEFAULT_TYPE) -> None:
        service.process_next()

    if application.job_queue is None:
        logging.getLogger(__name__).warning("JobQueue недоступен, метаданные ссылок не обрабатываются")
        return
    application.job_queue.run_repeating(
        process_link_metadata,
        interval=LINK_METADATA_INTERVAL_SECONDS,
        first=LINK_METADATA_INTERVAL_SECONDS,
        name=LINK_METADATA_JOB_NAME,
    )


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
    link_metadata_service = LinkMetadataService(LinkMetadataRepository(engine))
    application = build_application(settings, capture_service, link_metadata_service)
    logging.getLogger(__name__).info("SecondBrain запускает Telegram polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
