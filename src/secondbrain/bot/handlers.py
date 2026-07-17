from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from secondbrain.bot.navigation import (
    NAVIGATION_TEXTS,
    PROCESSED_EDIT_TEXT_KEY,
    SEARCH_QUERY_KEY,
    SEARCH_TEXT_KEY,
    TAG_CREATE_TEXT_KEY,
    TAG_RENAME_TEXT_KEY,
)
from secondbrain.services.capture import CaptureService
from secondbrain.services.inbox import (
    InboxService,
    build_inbox_keyboard,
    build_processed_keyboard,
    build_processed_review_keyboard,
    build_processed_tag_selection_keyboard,
    build_search_results_keyboard,
    build_tag_management_keyboard,
    build_tag_selection_keyboard,
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
        if inbox_service is not None and context.user_data.get(SEARCH_TEXT_KEY):
            page = inbox_service.build_search_page(query=message.text)
            if page.text == "Введите текст для поиска":
                await message.reply_text(page.text, disable_notification=True)
                return
            context.user_data.pop(SEARCH_TEXT_KEY, None)
            context.user_data[SEARCH_QUERY_KEY] = message.text
            await message.reply_text(
                page.text,
                reply_markup=build_search_results_keyboard(page),
                disable_notification=True,
            )
            return
        tag_rename_state = context.user_data.get(TAG_RENAME_TEXT_KEY)
        if inbox_service is not None and isinstance(tag_rename_state, dict):
            scope = tag_rename_state.get("scope")
            record_id = tag_rename_state.get("record_id")
            page = tag_rename_state.get("page", 0)
            tag_id = tag_rename_state.get("tag_id")
            if (
                scope in {"inbox", "processed"}
                and isinstance(record_id, int)
                and isinstance(page, int)
                and isinstance(tag_id, int)
            ):
                renamed = inbox_service.rename_tag(tag_id=tag_id, name=message.text)
                if not renamed:
                    await message.reply_text(
                        "Не удалось переименовать тег. Проверьте длину и уникальность названия.",
                        disable_notification=True,
                    )
                    return
                context.user_data.pop(TAG_RENAME_TEXT_KEY, None)
                await message.reply_text(
                    "Управление тегами",
                    reply_markup=build_tag_management_keyboard(
                        scope=scope,
                        record_id=record_id,
                        page=page,
                        tags=inbox_service.list_tags(),
                    ),
                    disable_notification=True,
                )
                return
        tag_create_state = context.user_data.get(TAG_CREATE_TEXT_KEY)
        if inbox_service is not None and isinstance(tag_create_state, dict):
            scope = tag_create_state.get("scope")
            record_id = tag_create_state.get("record_id")
            page = tag_create_state.get("page", 0)
            if scope in {"inbox", "processed"} and isinstance(record_id, int) and isinstance(page, int):
                created = inbox_service.create_tag(name=message.text)
                if created is None:
                    await message.reply_text(
                        "Не удалось создать тег. Проверьте длину и уникальность названия.",
                        disable_notification=True,
                    )
                    return
                context.user_data.pop(TAG_CREATE_TEXT_KEY, None)
                if scope == "processed":
                    key = f"processed_tags:{record_id}"
                    selected = context.user_data.setdefault(key, set())
                    if not isinstance(selected, set):
                        selected = set()
                        context.user_data[key] = selected
                    selected.add(created.tag_id)
                    text = inbox_service.build_processed_review(record_id)
                    current_tag_ids = inbox_service.processed_tag_ids(record_id)
                    if text is None or current_tag_ids is None:
                        page_data = inbox_service.build_processed_page(page)
                        await message.reply_text(
                            page_data.text,
                            reply_markup=build_processed_keyboard(page_data),
                            disable_notification=True,
                        )
                        return
                    await message.reply_text(
                        text,
                        reply_markup=build_processed_tag_selection_keyboard(
                            record_id=record_id,
                            page=page,
                            tags=inbox_service.list_tags(),
                            selected_tag_ids=selected,
                        ),
                        disable_notification=True,
                    )
                    return
                key = f"inbox_tags:{record_id}"
                selected = context.user_data.setdefault(key, set())
                if not isinstance(selected, set):
                    selected = set()
                    context.user_data[key] = selected
                selected.add(created.tag_id)
                text = inbox_service.build_review(record_id)
                if text is None:
                    page_data = inbox_service.build_page(page)
                    await message.reply_text(
                        page_data.text,
                        reply_markup=build_inbox_keyboard(page_data),
                        disable_notification=True,
                    )
                    return
                await message.reply_text(
                    text,
                    reply_markup=build_tag_selection_keyboard(
                        record_id=record_id,
                        page=page,
                        tags=inbox_service.list_tags(),
                        selected_tag_ids=selected,
                    ),
                    disable_notification=True,
                )
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
