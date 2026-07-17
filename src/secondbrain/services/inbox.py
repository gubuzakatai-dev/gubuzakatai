from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from secondbrain.models.records import InboxNextReview, InboxPage, ProcessedPage, TagOption, TagSearchPage
from secondbrain.storage.database import utc_now_text
from secondbrain.storage.repositories import InboxRepository

MAX_RECORDS_PER_PAGE = 10
MAX_INBOX_MESSAGE_LENGTH = 3500
MAX_PROCESSED_MESSAGE_LENGTH = 3500


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

    def build_processed_page(self, page: int = 0) -> ProcessedPage:
        records = self._repository.list_processed()
        if not records:
            return ProcessedPage(
                text="Разобранных записей нет",
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
        lines = ["Разобранные"]
        record_ids: list[int] = []
        for number, record in enumerate(selected, start=1):
            tag_line = f"Теги: {', '.join(record.tags)}" if record.tags else "Теги: нет"
            candidate_lines = [*lines, "", f"{number}. {record.display_text}", tag_line]
            if record_ids and len("\n".join(candidate_lines)) > MAX_PROCESSED_MESSAGE_LENGTH:
                break
            lines = candidate_lines
            record_ids.append(record.record_id)

        end = start + len(record_ids)
        return ProcessedPage(
            text="\n".join(lines),
            record_ids=tuple(record_ids),
            page=page,
            has_previous=page > 0,
            has_next=end < len(records),
        )

    def build_tag_search_page(self, *, tag_id: int, page: int = 0) -> TagSearchPage:
        tag_name = next((tag.name for tag in self.list_tags() if tag.tag_id == tag_id), "тег")
        records = self._repository.list_processed_by_tag(tag_id)
        if not records:
            return TagSearchPage(
                text="Ничего не найдено",
                record_ids=(),
                tag_id=tag_id,
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
        lines = [f"Тег: {tag_name}"]
        record_ids: list[int] = []
        for number, record in enumerate(selected, start=1):
            tag_line = f"Теги: {', '.join(record.tags)}" if record.tags else "Теги: нет"
            candidate_lines = [*lines, "", f"{number}. {record.display_text}", tag_line]
            if record_ids and len("\n".join(candidate_lines)) > MAX_PROCESSED_MESSAGE_LENGTH:
                break
            lines = candidate_lines
            record_ids.append(record.record_id)

        end = start + len(record_ids)
        return TagSearchPage(
            text="\n".join(lines),
            record_ids=tuple(record_ids),
            tag_id=tag_id,
            page=page,
            has_previous=page > 0,
            has_next=end < len(records),
        )

    def build_processed_review(self, record_id: int) -> str | None:
        record = self._repository.get_processed_record(record_id)
        if record is None:
            return None
        tag_line = f"Теги: {', '.join(record.tags)}" if record.tags else "Теги: нет"
        return f"{record.display_text}\n\n{tag_line}"

    def processed_tag_ids(self, record_id: int) -> set[int] | None:
        record = self._repository.get_processed_record(record_id)
        if record is None:
            return None
        tag_ids_by_name = {tag.name: tag.tag_id for tag in self.list_tags()}
        return {tag_ids_by_name[name] for name in record.tags if name in tag_ids_by_name}

    def build_review(self, record_id: int) -> str | None:
        record = self._repository.get_inbox_record(record_id)
        if record is None:
            return None
        return record.display_text

    def build_next_review(self, page: int) -> InboxNextReview:
        page_data = self.build_page(page)
        if not page_data.record_ids:
            return InboxNextReview(page=page_data, record_id=None, text=None)

        record_id = page_data.record_ids[0]
        return InboxNextReview(
            page=page_data,
            record_id=record_id,
            text=self.build_review(record_id),
        )

    def convert_to_task(self, *, record_id: int, task_list: str) -> bool:
        return self._repository.convert_inbox_to_task(
            record_id=record_id,
            task_list=task_list,
            changed_at=utc_now_text(),
        )

    def convert_processed_to_task(self, *, record_id: int, task_list: str) -> bool:
        return self._repository.convert_processed_to_task(
            record_id=record_id,
            task_list=task_list,
            changed_at=utc_now_text(),
        )

    def list_tags(self) -> list[TagOption]:
        return self._repository.list_tags()

    def create_tag(self, *, name: str) -> TagOption | None:
        return self._repository.create_tag(name=name, changed_at=utc_now_text())

    def rename_tag(self, *, tag_id: int, name: str) -> bool:
        return self._repository.rename_tag(
            tag_id=tag_id,
            name=name,
            changed_at=utc_now_text(),
        )

    def delete_tag(self, *, tag_id: int) -> bool:
        return self._repository.delete_tag(tag_id=tag_id)

    def save_tags(self, *, record_id: int, tag_ids: tuple[int, ...]) -> bool:
        return self._repository.mark_inbox_processed_with_tags(
            record_id=record_id,
            tag_ids=tag_ids,
            changed_at=utc_now_text(),
        )

    def update_processed_tags(self, *, record_id: int, tag_ids: tuple[int, ...]) -> bool:
        return self._repository.update_processed_tags(
            record_id=record_id,
            tag_ids=tag_ids,
            changed_at=utc_now_text(),
        )

    def update_processed_text(self, *, record_id: int, display_text: str) -> bool:
        return self._repository.update_processed_text(
            record_id=record_id,
            display_text=display_text,
            changed_at=utc_now_text(),
        )

    def move_to_trash(self, *, record_id: int) -> bool:
        return self._repository.move_inbox_to_trash(record_id=record_id, trashed_at=utc_now_text())

    def move_processed_to_trash(self, *, record_id: int) -> bool:
        return self._repository.move_processed_to_trash(record_id=record_id, trashed_at=utc_now_text())


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


def build_processed_keyboard(page: ProcessedPage) -> InlineKeyboardMarkup:
    if not page.record_ids:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="folders:open")]])

    rows = [
        [
            InlineKeyboardButton(
                str(number),
                callback_data=f"processed:record:{record_id}:page:{page.page}",
            )
        ]
        for number, record_id in enumerate(page.record_ids, start=1)
    ]
    navigation: list[InlineKeyboardButton] = []
    if page.has_previous:
        navigation.append(InlineKeyboardButton("←", callback_data=f"processed:page:{page.page - 1}"))
    if page.has_next:
        navigation.append(InlineKeyboardButton("→", callback_data=f"processed:page:{page.page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Назад", callback_data="folders:open")])
    return InlineKeyboardMarkup(rows)


def build_processed_review_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Изменить текст", callback_data=f"processed:edit_text:{record_id}:{page}")],
            [InlineKeyboardButton("Изменить теги", callback_data=f"processed:tags:{record_id}:{page}")],
            [InlineKeyboardButton("Сделать задачей", callback_data=f"processed:task:{record_id}:{page}")],
            [InlineKeyboardButton("Удалить в корзину", callback_data=f"processed:trash:{record_id}:{page}")],
            [InlineKeyboardButton("Назад", callback_data=f"processed:page:{page}")],
        ]
    )


def build_processed_text_edit_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Отмена", callback_data=f"processed:record:{record_id}:page:{page}")]]
    )


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


def build_task_list_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сегодня", callback_data=f"inbox:task_list:{record_id}:today:{page}")],
            [InlineKeyboardButton("Завтра", callback_data=f"inbox:task_list:{record_id}:tomorrow:{page}")],
            [InlineKeyboardButton("Неделя", callback_data=f"inbox:task_list:{record_id}:week:{page}")],
            [InlineKeyboardButton("Назад", callback_data=f"inbox:review:{record_id}:page:{page}")],
        ]
    )


def build_processed_task_list_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Сегодня", callback_data=f"processed:task_list:{record_id}:today:{page}")],
            [InlineKeyboardButton("Завтра", callback_data=f"processed:task_list:{record_id}:tomorrow:{page}")],
            [InlineKeyboardButton("Неделя", callback_data=f"processed:task_list:{record_id}:week:{page}")],
            [InlineKeyboardButton("Назад", callback_data=f"processed:record:{record_id}:page:{page}")],
        ]
    )


def build_tag_selection_keyboard(
    *,
    record_id: int,
    page: int,
    tags: list[TagOption],
    selected_tag_ids: set[int],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{'✓ ' if tag.tag_id in selected_tag_ids else ''}{tag.name}",
                callback_data=f"inbox:tag_toggle:{record_id}:{tag.tag_id}:{page}",
            )
        ]
        for tag in tags
    ]
    rows.append([InlineKeyboardButton("Новый тег", callback_data=f"tags:new:inbox:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Управление тегами", callback_data=f"tags:manage:inbox:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Сохранить", callback_data=f"inbox:tag_save:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Назад", callback_data=f"inbox:review:{record_id}:page:{page}")])
    return InlineKeyboardMarkup(rows)


def build_processed_tag_selection_keyboard(
    *,
    record_id: int,
    page: int,
    tags: list[TagOption],
    selected_tag_ids: set[int],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"{'✓ ' if tag.tag_id in selected_tag_ids else ''}{tag.name}",
                callback_data=f"processed:tag_toggle:{record_id}:{tag.tag_id}:{page}",
            )
        ]
        for tag in tags
    ]
    rows.append([InlineKeyboardButton("Новый тег", callback_data=f"tags:new:processed:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Управление тегами", callback_data=f"tags:manage:processed:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Сохранить", callback_data=f"processed:tag_save:{record_id}:{page}")])
    rows.append([InlineKeyboardButton("Назад", callback_data=f"processed:record:{record_id}:page:{page}")])
    return InlineKeyboardMarkup(rows)


def build_tag_search_keyboard(tags: list[TagOption]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(tag.name, callback_data=f"tags:select:{tag.tag_id}:page:0")]
        for tag in tags
    ]
    rows.append([InlineKeyboardButton("Назад", callback_data="folders:open")])
    return InlineKeyboardMarkup(rows)


def build_tag_search_results_keyboard(page: TagSearchPage) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    navigation: list[InlineKeyboardButton] = []
    if page.has_previous:
        navigation.append(
            InlineKeyboardButton("←", callback_data=f"tags:select:{page.tag_id}:page:{page.page - 1}")
        )
    if page.has_next:
        navigation.append(
            InlineKeyboardButton("→", callback_data=f"tags:select:{page.tag_id}:page:{page.page + 1}")
        )
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Новый поиск", callback_data="folders:tags")])
    rows.append([InlineKeyboardButton("Назад", callback_data="folders:open")])
    return InlineKeyboardMarkup(rows)


def build_tag_management_keyboard(
    *,
    scope: str,
    record_id: int,
    page: int,
    tags: list[TagOption],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                f"Переименовать: {tag.name}",
                callback_data=f"tags:rename:{scope}:{record_id}:{page}:{tag.tag_id}",
            ),
            InlineKeyboardButton(
                "Удалить",
                callback_data=f"tags:delete:{scope}:{record_id}:{page}:{tag.tag_id}",
            ),
        ]
        for tag in tags
    ]
    rows.append([InlineKeyboardButton("Назад", callback_data=f"tags:back:{scope}:{record_id}:{page}")])
    return InlineKeyboardMarkup(rows)


def build_tag_delete_confirmation_keyboard(
    *,
    scope: str,
    record_id: int,
    page: int,
    tag_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Удалить",
                    callback_data=f"tags:delete_confirm:{scope}:{record_id}:{page}:{tag_id}",
                )
            ],
            [InlineKeyboardButton("Отмена", callback_data=f"tags:manage:{scope}:{record_id}:{page}")],
        ]
    )


def build_trash_confirmation_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Удалить", callback_data=f"inbox:trash_confirm:{record_id}:{page}")],
            [InlineKeyboardButton("Отмена", callback_data=f"inbox:review:{record_id}:page:{page}")],
        ]
    )


def build_processed_trash_confirmation_keyboard(record_id: int, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Удалить", callback_data=f"processed:trash_confirm:{record_id}:{page}")],
            [InlineKeyboardButton("Отмена", callback_data=f"processed:record:{record_id}:page:{page}")],
        ]
    )
