from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from secondbrain.services.inbox import (
    InboxService,
    build_inbox_keyboard,
    build_record_review_keyboard,
    build_review_routes_keyboard,
    build_tag_selection_keyboard,
    build_task_list_keyboard,
)

NAVIGATION_TEXTS = frozenset({"Папки"})


def register_navigation_handlers(
    application: Application,
    *,
    allowed_user_id: int,
    inbox_service: InboxService,
) -> None:
    owner = filters.User(user_id=allowed_user_id)

    async def open_folders(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        await message.reply_text(
            "Папки",
            reply_markup=_folders_keyboard(inbox_count=inbox_service.count()),
            disable_notification=True,
        )

    async def folders_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        await query.edit_message_text(
            "Папки",
            reply_markup=_folders_keyboard(inbox_count=inbox_service.count()),
        )

    async def open_inbox_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        await query.answer()
        page = inbox_service.build_page(_page_from_callback(query.data))
        await query.edit_message_text(page.text, reply_markup=build_inbox_keyboard(page))

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

    async def convert_to_task_callback(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
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
        next_page = inbox_service.build_page(page)
        if next_page.record_ids:
            next_record_id = next_page.record_ids[0]
            text = inbox_service.build_review(next_record_id)
            if text is not None:
                await query.edit_message_text(
                    text,
                    reply_markup=build_record_review_keyboard(next_record_id, next_page.page),
                )
                return
        await query.edit_message_text(next_page.text, reply_markup=build_inbox_keyboard(next_page))

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
        next_page = inbox_service.build_page(page)
        if next_page.record_ids:
            next_record_id = next_page.record_ids[0]
            text = inbox_service.build_review(next_record_id)
            if text is not None:
                await query.edit_message_text(
                    text,
                    reply_markup=build_record_review_keyboard(next_record_id, next_page.page),
                )
                return
        await query.edit_message_text(next_page.text, reply_markup=build_inbox_keyboard(next_page))

    application.add_handler(MessageHandler(owner & filters.Regex("^Папки$"), open_folders), group=0)
    application.add_handler(CallbackQueryHandler(folders_callback, pattern="^folders:open$"), group=0)
    application.add_handler(CallbackQueryHandler(open_inbox_callback, pattern="^inbox:page:"), group=0)
    application.add_handler(
        CallbackQueryHandler(open_record_callback, pattern="^inbox:record:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_review_routes_callback, pattern="^inbox:review:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(open_task_lists_callback, pattern="^inbox:task:"), group=0
    )
    application.add_handler(
        CallbackQueryHandler(convert_to_task_callback, pattern="^inbox:task_list:"), group=0
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


def _folders_keyboard(*, inbox_count: int) -> InlineKeyboardMarkup:
    inbox_label = f"Входящие ({inbox_count})" if inbox_count else "Входящие"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(inbox_label, callback_data="inbox:page:0")],
            [InlineKeyboardButton("Разобранные", callback_data="folders:processed")],
            [InlineKeyboardButton("Поиск по тегам", callback_data="folders:tags")],
            [InlineKeyboardButton("Назад", callback_data="main:open")],
        ]
    )


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


def _selected_tags(context: ContextTypes.DEFAULT_TYPE, record_id: int) -> set[int]:
    key = _tag_session_key(record_id)
    selected = context.user_data.setdefault(key, set())
    if not isinstance(selected, set):
        selected = set()
        context.user_data[key] = selected
    return selected


def _tag_session_key(record_id: int) -> str:
    return f"inbox_tags:{record_id}"
