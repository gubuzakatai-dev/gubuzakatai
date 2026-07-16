from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from secondbrain.bot.navigation import NAVIGATION_TEXTS, PROCESSED_EDIT_TEXT_KEY
from secondbrain.services.capture import CaptureService
from secondbrain.services.inbox import (
    InboxService,
    build_processed_review_keyboard,
)

VOICE_REPLY = (
    "В первой версии отправьте текст. "
    "Для диктовки используйте микрофон на клавиатуре телефона"
)


def register_capture_handlers(
    application: Application,
    *,
    allowed_user_id: int,
    capture_service: CaptureService,
    inbox_service: InboxService | None = None,
) -> None:
    owner = filters.User(user_id=allowed_user_id)

    async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None or message.text is None:
            return
        edit_state = context.user_data.get(PROCESSED_EDIT_TEXT_KEY)
        if inbox_service is not None and isinstance(edit_state, dict):
            record_id = edit_state.get("record_id")
            page = edit_state.get("page", 0)
            if isinstance(record_id, int) and isinstance(page, int):
                updated = inbox_service.update_processed_text(
                    record_id=record_id,
                    display_text=message.text,
                )
                context.user_data.pop(PROCESSED_EDIT_TEXT_KEY, None)
                text = inbox_service.build_processed_review(record_id)
                if updated and text is not None:
                    await message.reply_text(
                        text,
                        reply_markup=build_processed_review_keyboard(record_id, page),
                        disable_notification=True,
                    )
                    return
                await message.reply_text(
                    "Запись уже недоступна",
                    disable_notification=True,
                )
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

    navigation_texts = filters.Regex(f"^({'|'.join(NAVIGATION_TEXTS)})$")
    application.add_handler(
        MessageHandler(owner & filters.TEXT & ~filters.COMMAND & ~navigation_texts, receive_text)
    )
    application.add_handler(MessageHandler(owner & filters.VOICE, reject_voice))
