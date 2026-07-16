from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from secondbrain.services.inbox import InboxService, build_inbox_keyboard

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

    application.add_handler(MessageHandler(owner & filters.Regex("^Папки$"), open_folders), group=0)
    application.add_handler(CallbackQueryHandler(folders_callback, pattern="^folders:open$"), group=0)
    application.add_handler(CallbackQueryHandler(open_inbox_callback, pattern="^inbox:page:"), group=0)


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
