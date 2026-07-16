from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from secondbrain.models.records import InboxPage
from secondbrain.storage.repositories import InboxRepository

MAX_RECORDS_PER_PAGE = 10
MAX_INBOX_MESSAGE_LENGTH = 3500


class InboxService:
    def __init__(self, repository: InboxRepository) -> None:
        self._repository = repository

    def build_page(self, page: int = 0) -> InboxPage:
        records = self._repository.list_inbox()
        if not records:
            return InboxPage(
                text="Входящие пусты",
                record_ids=(),
                page=0,
                has_previous=False,
                has_next=False,
            )

        page = max(page, 0)
        start = page * MAX_RECORDS_PER_PAGE
        if start >= len(records):
            page = max((len(records) - 1) // MAX_RECORDS_PER_PAGE, 0)
            start = page * MAX_RECORDS_PER_PAGE

        selected = records[start : start + MAX_RECORDS_PER_PAGE]
        lines = ["Входящие"]
        record_ids: list[int] = []
        for number, record in enumerate(selected, start=1):
            candidate_lines = [*lines, "", f"{number}. {record.display_text}"]
            if record_ids and len("\n".join(candidate_lines)) > MAX_INBOX_MESSAGE_LENGTH:
                break
            lines = candidate_lines
            record_ids.append(record.record_id)

        end = start + len(record_ids)
        return InboxPage(
            text="\n".join(lines),
            record_ids=tuple(record_ids),
            page=page,
            has_previous=page > 0,
            has_next=end < len(records),
        )

    def count(self) -> int:
        return self._repository.count_inbox()

    def build_review(self, record_id: int) -> str | None:
        record = self._repository.get_inbox_record(record_id)
        if record is None:
            return None
        return record.display_text


def build_inbox_keyboard(page: InboxPage) -> InlineKeyboardMarkup:
    if not page.record_ids:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="folders:open")]])

    rows = [
        [
            InlineKeyboardButton(
                str(number),
                callback_data=f"inbox:record:{record_id}:page:{page.page}",
            )
        ]
        for number, record_id in enumerate(page.record_ids, start=1)
    ]
    navigation: list[InlineKeyboardButton] = []
    if page.has_previous:
        navigation.append(InlineKeyboardButton("←", callback_data=f"inbox:page:{page.page - 1}"))
    if page.has_next:
        navigation.append(InlineKeyboardButton("→", callback_data=f"inbox:page:{page.page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Назад", callback_data="folders:open")])
    return InlineKeyboardMarkup(rows)


def build_record_review_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Разобрать", callback_data=f"inbox:review:{record_id}:page:{page}")],
            [InlineKeyboardButton("Назад", callback_data=f"inbox:page:{page}")],
        ]
    )


def build_review_routes_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сделать задачей", callback_data=f"inbox:task:{record_id}:page:{page}")],
            [InlineKeyboardButton("Разобрать по тегам", callback_data=f"inbox:tags:{record_id}:page:{page}")],
            [InlineKeyboardButton("Удалить в корзину", callback_data=f"inbox:trash:{record_id}:page:{page}")],
            [InlineKeyboardButton("Назад", callback_data=f"inbox:record:{record_id}:page:{page}")],
        ]
    )
