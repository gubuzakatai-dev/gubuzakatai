from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from secondbrain.services.capture import CaptureService

VOICE_REPLY = (
    "В первой версии отправьте текст. "
    "Для диктовки используйте микрофон на клавиатуре телефона"
)


def register_capture_handlers(
    application: Application,
    *,
    allowed_user_id: int,
    capture_service: CaptureService,
) -> None:
    owner = filters.User(user_id=allowed_user_id)

    async def receive_text(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.text is None:
            return
        capture_service.capture_text(
            chat_id=message.chat_id,
            message_id=message.message_id,
            raw_text=message.text,
            telegram_sent_at=message.date,
        )

    async def reject_voice(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is not None:
            await message.reply_text(VOICE_REPLY, disable_notification=True)

    application.add_handler(MessageHandler(owner & filters.TEXT & ~filters.COMMAND, receive_text))
    application.add_handler(MessageHandler(owner & filters.VOICE, reject_voice))
