from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from secondbrain.services.evening_reminder import EveningReminderService
from secondbrain.services.inbox import (
    InboxService,
    build_inbox_keyboard,
    build_processed_keyboard,
    build_processed_review_keyboard,
    build_processed_tag_selection_keyboard,
    build_processed_task_list_keyboard,
    build_processed_text_edit_keyboard,
    build_processed_trash_confirmation_keyboard,
    build_record_review_keyboard,
    build_review_routes_keyboard,
    build_tag_selection_keyboard,
    build_task_list_keyboard,
    build_trash_confirmation_keyboard,
)
from secondbrain.services.tasks import TaskService, build_task_page_keyboard

NAVIGATION_TEXTS = frozenset({"Сегодня", "Папки"})
PROCESSED_EDIT_TEXT_KEY = "processed_edit_text"


def register_navigation_handlers(
    application: Application,
    *,
    allowed_user_id: int,
    inbox_service: InboxService,
    evening_reminder_service: EveningReminderService | None = None,
    task_service: TaskService | None = None,
) -> None:
    owner = filters.User(user_id=allowed_user_id)

    async def open_folders(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            "Папки",
            reply_markup=build_folders_keyboard(inbox_count=inbox_service.count()),
            disable_notification=True,
        )

    async def folders_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        await query.edit_message_text(
            "Папки",
            reply_markup=build_folders_keyboard(inbox_count=inbox_service.count()),
        )

    async def open_today(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if task_service is None:
            return
        message = update.effective_message
        if message is None:
            return
        page = task_service.build_page("today")
        await message.reply_text(
            page.text,
            reply_markup=build_task_page_keyboard("today", page),
            disable_notification=True,
        )

    async def open_today_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if task_service is None:
            return
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        page = task_service.build_page("today", _page_from_callback(query.data))
        await query.edit_message_text(page.text, reply_markup=build_task_page_keyboard("today", page))

    async def open_inbox_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        page = inbox_service.build_page(_page_from_callback(query.data))
        await query.edit_message_text(page.text, reply_markup=build_inbox_keyboard(page))

    async def open_processed_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        page = inbox_service.build_processed_page(_page_from_callback(query.data))
        await query.edit_message_text(page.text, reply_markup=build_processed_keyboard(page))

    async def open_processed_record_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        await query.edit_message_text(
            text,
            reply_markup=build_processed_review_keyboard(record_id, page),
        )

    async def open_processed_text_edit_callback(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        context.user_data[PROCESSED_EDIT_TEXT_KEY] = {"record_id": record_id, "page": page}
        await query.edit_message_text(
            f"{text}\n\nОтправьте новый текст для этой записи.",
            reply_markup=build_processed_text_edit_keyboard(record_id, page),
        )

    async def open_processed_task_lists_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        await query.edit_message_text(text, reply_markup=build_processed_task_list_keyboard(record_id, page))

    async def convert_processed_to_task_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, task_list, page = _task_list_from_callback(query.data)
        if task_list is None:
            await query.answer()
            return
        converted = inbox_service.convert_processed_to_task(record_id=record_id, task_list=task_list)
        await query.answer("Сохранено" if converted else "Запись уже недоступна")
        page_data = inbox_service.build_processed_page(page)
        await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))

    async def open_processed_tag_selection_callback(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_processed_review(record_id)
        current_tag_ids = inbox_service.processed_tag_ids(record_id)
        if text is None or current_tag_ids is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        context.user_data[_tag_session_key(record_id, prefix="processed_tags")] = set(current_tag_ids)
        await query.edit_message_text(
            text,
            reply_markup=build_processed_tag_selection_keyboard(
                record_id=record_id,
                page=page,
                tags=inbox_service.list_tags(),
                selected_tag_ids=set(current_tag_ids),
            ),
        )

    async def toggle_processed_tag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, tag_id, page = _tag_toggle_from_callback(query.data)
        selected = _selected_tags(context, record_id, prefix="processed_tags")
        if tag_id in selected:
            selected.remove(tag_id)
        else:
            selected.add(tag_id)
        await query.answer()
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        await query.edit_message_text(
            text,
            reply_markup=build_processed_tag_selection_keyboard(
                record_id=record_id,
                page=page,
                tags=inbox_service.list_tags(),
                selected_tag_ids=selected,
            ),
        )

    async def save_processed_tags_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, page = _record_and_page_from_callback(query.data)
        selected = _selected_tags(context, record_id, prefix="processed_tags")
        if not selected:
            await query.answer("Выберите хотя бы один тег")
            return
        saved = inbox_service.update_processed_tags(record_id=record_id, tag_ids=tuple(sorted(selected)))
        context.user_data.pop(_tag_session_key(record_id, prefix="processed_tags"), None)
        await query.answer("Сохранено" if saved else "Запись уже недоступна")
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        await query.edit_message_text(
            text,
            reply_markup=build_processed_review_keyboard(record_id, page),
        )

    async def open_processed_trash_confirmation_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_processed_review(record_id)
        if text is None:
            page_data = inbox_service.build_processed_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))
            return
        await query.edit_message_text(
            f"{text}\n\nУдалить запись в корзину?",
            reply_markup=build_processed_trash_confirmation_keyboard(record_id, page),
        )

    async def confirm_processed_trash_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, page = _record_and_page_from_callback(query.data)
        moved = inbox_service.move_processed_to_trash(record_id=record_id)
        await query.answer("Удалено" if moved else "Запись уже недоступна")
        page_data = inbox_service.build_processed_page(page)
        await query.edit_message_text(page_data.text, reply_markup=build_processed_keyboard(page_data))

    async def open_record_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await query.edit_message_text(
            text,
            reply_markup=build_record_review_keyboard(record_id, page),
        )

    async def open_review_routes_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await query.edit_message_text(text, reply_markup=build_review_routes_keyboard(record_id, page))

    async def open_task_lists_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await query.edit_message_text(text, reply_markup=build_task_list_keyboard(record_id, page))

    async def convert_to_task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, task_list, page = _task_list_from_callback(query.data)
        if task_list is None:
            await query.answer()
            return
        converted = inbox_service.convert_to_task(record_id=record_id, task_list=task_list)
        await query.answer("Сохранено")
        if not converted:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await _delete_stale_evening_reminder(
            context,
            evening_reminder_service,
            allowed_user_id=allowed_user_id,
        )
        await _open_next_review(query, inbox_service, page)

    async def open_tag_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        selected = _selected_tags(context, record_id)
        await query.edit_message_text(
            text,
            reply_markup=build_tag_selection_keyboard(
                record_id=record_id,
                page=page,
                tags=inbox_service.list_tags(),
                selected_tag_ids=selected,
            ),
        )

    async def toggle_tag_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, tag_id, page = _tag_toggle_from_callback(query.data)
        selected = _selected_tags(context, record_id)
        if tag_id in selected:
            selected.remove(tag_id)
        else:
            selected.add(tag_id)
        await query.answer()
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await query.edit_message_text(
            text,
            reply_markup=build_tag_selection_keyboard(
                record_id=record_id,
                page=page,
                tags=inbox_service.list_tags(),
                selected_tag_ids=selected,
            ),
        )

    async def save_tags_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, page = _record_and_page_from_callback(query.data)
        selected = _selected_tags(context, record_id)
        if not selected:
            await query.answer("Выберите хотя бы один тег")
            return
        saved = inbox_service.save_tags(record_id=record_id, tag_ids=tuple(sorted(selected)))
        context.user_data.pop(_tag_session_key(record_id), None)
        await query.answer("Сохранено")
        if not saved:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await _delete_stale_evening_reminder(
            context,
            evening_reminder_service,
            allowed_user_id=allowed_user_id,
        )
        await _open_next_review(query, inbox_service, page)

    async def open_trash_confirmation_callback(
        update: Update, _context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        record_id, page = _record_and_page_from_callback(query.data)
        text = inbox_service.build_review(record_id)
        if text is None:
            page_data = inbox_service.build_page(page)
            await query.edit_message_text(page_data.text, reply_markup=build_inbox_keyboard(page_data))
            return
        await query.edit_message_text(
            f"{text}\n\nУдалить запись в корзину?",
            reply_markup=build_trash_confirmation_keyboard(record_id, page),
        )

    async def confirm_trash_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        record_id, page = _record_and_page_from_callback(query.data)
        moved = inbox_service.move_to_trash(record_id=record_id)
        await query.answer("Удалено" if moved else "Запись уже недоступна")
        if moved:
            await _delete_stale_evening_reminder(
                context,
                evening_reminder_service,
                allowed_user_id=allowed_user_id,
            )
        await _open_next_review(query, inbox_service, page)

    async def evening_reminder_review_callback(
        update: Update,
        _context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        if evening_reminder_service is not None:
            evening_reminder_service.clear_message(telegram_message_id=query.message.message_id)
        await query.message.delete()
        await _send_next_review(query, inbox_service)

    application.add_handler(MessageHandler(owner & filters.Regex("^Папки$"), open_folders), group=0)
    if task_service is not None:
        application.add_handler(MessageHandler(owner & filters.Regex("^Сегодня$"), open_today), group=0)
        application.add_handler(
            CallbackQueryHandler(open_today_callback, pattern="^tasks:today:page:"),
            group=0,
        )
    application.add_handler(CallbackQueryHandler(folders_callback, pattern="^folders:open$"), group=0)
    application.add_handler(
        CallbackQueryHandler(open_processed_callback, pattern="^(folders:processed|processed:page:)"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(open_processed_record_callback, pattern="^processed:record:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(open_processed_text_edit_callback, pattern="^processed:edit_text:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(convert_processed_to_task_callback, pattern="^processed:task_list:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(open_processed_task_lists_callback, pattern="^processed:task:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(toggle_processed_tag_callback, pattern="^processed:tag_toggle:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(save_processed_tags_callback, pattern="^processed:tag_save:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(open_processed_tag_selection_callback, pattern="^processed:tags:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(confirm_processed_trash_callback, pattern="^processed:trash_confirm:"),
        group=0,
    )
    application.add_handler(
        CallbackQueryHandler(open_processed_trash_confirmation_callback, pattern="^processed:trash:"),
        group=0,
    )
    application.add_handler(CallbackQueryHandler(open_inbox_callback, pattern="^inbox:page:"), group=0)
    application.add_handler(
        CallbackQueryHandler(open_record_callback, pattern="^inbox:record:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_review_routes_callback, pattern="^inbox:review:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(convert_to_task_callback, pattern="^inbox:task_list:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_task_lists_callback, pattern="^inbox:task:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_tag_selection_callback, pattern="^inbox:tags:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(toggle_tag_callback, pattern="^inbox:tag_toggle:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(save_tags_callback, pattern="^inbox:tag_save:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(confirm_trash_callback, pattern="^inbox:trash_confirm:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_trash_confirmation_callback, pattern="^inbox:trash:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(evening_reminder_review_callback, pattern="^evening_reminder:review$"),
        group=0,
    )


def build_folders_keyboard(*, inbox_count: int) -> InlineKeyboardMarkup:
    inbox_label = f"Входящие ({inbox_count})" if inbox_count else "Входящие"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(inbox_label, callback_data="inbox:page:0")],
            [InlineKeyboardButton("Разобранные", callback_data="folders:processed")],
            [InlineKeyboardButton("Поиск по тегам", callback_data="folders:tags")],
            [InlineKeyboardButton("Назад", callback_data="main:open")],
        ]
    )


async def _open_next_review(query, inbox_service: InboxService, page: int) -> None:
    next_review = inbox_service.build_next_review(page)
    if next_review.record_id is not None and next_review.text is not None:
        await query.edit_message_text(
            next_review.text,
            reply_markup=build_record_review_keyboard(next_review.record_id, next_review.page.page),
        )
        return
    await query.edit_message_text(
        next_review.page.text,
        reply_markup=build_inbox_keyboard(next_review.page),
    )


async def _send_next_review(query, inbox_service: InboxService) -> None:
    if query.message is None:
        return
    next_review = inbox_service.build_next_review(0)
    if next_review.record_id is not None and next_review.text is not None:
        await query.message.chat.send_message(
            next_review.text,
            reply_markup=build_record_review_keyboard(next_review.record_id, next_review.page.page),
            disable_notification=True,
        )
        return
    await query.message.chat.send_message(
        next_review.page.text,
        reply_markup=build_inbox_keyboard(next_review.page),
        disable_notification=True,
    )


async def _delete_stale_evening_reminder(
    context: ContextTypes.DEFAULT_TYPE,
    evening_reminder_service: EveningReminderService | None,
    *,
    allowed_user_id: int,
) -> None:
    if evening_reminder_service is None or evening_reminder_service.count_inbox() > 0:
        return
    message_id = evening_reminder_service.get_active_message_id()
    if message_id is None:
        return
    try:
        await context.bot.delete_message(chat_id=allowed_user_id, message_id=message_id)
    except TelegramError:
        pass
    evening_reminder_service.clear_message(telegram_message_id=message_id)


def _page_from_callback(data: str | None) -> int:
    if data is None:
        return 0
    try:
        return int(data.rsplit(":", maxsplit=1)[-1])
    except ValueError:
        return 0


def _record_and_page_from_callback(data: str | None) -> tuple[int, int]:
    if data is None:
        return 0, 0
    parts = data.split(":")
    try:
        record_id = int(parts[2])
        page = int(parts[-1])
    except (IndexError, ValueError):
        return 0, 0
    return record_id, page


def _task_list_from_callback(data: str | None) -> tuple[int, str | None, int]:
    if data is None:
        return 0, None, 0
    parts = data.split(":")
    try:
        record_id = int(parts[2])
        task_list = parts[3]
        page = int(parts[4])
    except (IndexError, ValueError):
        return 0, None, 0
    if task_list not in {"today", "tomorrow", "week"}:
        return record_id, None, page
    return record_id, task_list, page


def _tag_toggle_from_callback(data: str | None) -> tuple[int, int, int]:
    if data is None:
        return 0, 0, 0
    parts = data.split(":")
    try:
        return int(parts[2]), int(parts[3]), int(parts[4])
    except (IndexError, ValueError):
        return 0, 0, 0


def _selected_tags(
    context: ContextTypes.DEFAULT_TYPE,
    record_id: int,
    *,
    prefix: str = "inbox_tags",
) -> set[int]:
    key = _tag_session_key(record_id, prefix=prefix)
    selected = context.user_data.setdefault(key, set())
    if not isinstance(selected, set):
        selected = set()
        context.user_data[key] = selected
    return selected


def _tag_session_key(record_id: int, *, prefix: str = "inbox_tags") -> str:
    return f"{prefix}:{record_id}"
