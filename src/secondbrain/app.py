import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, ContextTypes

from secondbrain.bot.handlers import register_capture_handlers
from secondbrain.bot.navigation import register_navigation_handlers
from secondbrain.config.settings import Settings, load_settings
from secondbrain.services.capture import CaptureService
from secondbrain.services.inbox import InboxService
from secondbrain.services.link_metadata import LinkMetadataService
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, InboxRepository, LinkMetadataRepository

LINK_METADATA_JOB_NAME = "link_metadata"
LINK_METADATA_INTERVAL_SECONDS = 60
CONFIRMATION_JOB_NAME = "pending_confirmations"
CONFIRMATION_INTERVAL_SECONDS = 5


def build_application(
    settings: Settings,
    capture_service: CaptureService | None = None,
    link_metadata_service: LinkMetadataService | None = None,
    inbox_service: InboxService | None = None,
) -> Application:
    """Build the Telegram application without starting network operations."""
    application = Application.builder().token(settings.telegram_bot_token).build()
    if inbox_service is not None:
        register_navigation_handlers(
            application,
            allowed_user_id=settings.telegram_allowed_user_id,
            inbox_service=inbox_service,
        )
    if capture_service is not None:
        register_capture_handlers(
            application,
            allowed_user_id=settings.telegram_allowed_user_id,
            capture_service=capture_service,
        )
    if link_metadata_service is not None:
        register_link_metadata_job(application, link_metadata_service)
    if capture_service is not None:
        register_confirmation_job(application, settings.telegram_allowed_user_id, capture_service)
    return application


def register_confirmation_job(
    application: Application,
    allowed_user_id: int,
    capture_service: CaptureService,
) -> None:
    async def process_pending_confirmations(context: ContextTypes.DEFAULT_TYPE) -> None:
        while pending := capture_service.get_next_unconfirmed(chat_id=allowed_user_id):
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Изменить", callback_data=f"edit:{pending.record_id}")]]
            )
            await context.bot.send_message(
                chat_id=pending.chat_id,
                text=f"{pending.display_text}\n\nСохранено: {pending.destination}",
                reply_markup=keyboard,
                disable_notification=True,
            )
            capture_service.mark_confirmation_sent(source_message_id=pending.source_message_id)

    if application.job_queue is None:
        logging.getLogger(__name__).warning("JobQueue недоступен, подтверждения не обрабатываются")
        return
    application.job_queue.run_repeating(
        process_pending_confirmations,
        interval=CONFIRMATION_INTERVAL_SECONDS,
        first=CONFIRMATION_INTERVAL_SECONDS,
        name=CONFIRMATION_JOB_NAME,
    )


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
    inbox_service = InboxService(InboxRepository(engine))
    application = build_application(settings, capture_service, link_metadata_service, inbox_service)
    logging.getLogger(__name__).info("SecondBrain запускает Telegram polling")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
