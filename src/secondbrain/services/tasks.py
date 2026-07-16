from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from secondbrain.models.records import TaskPage
from secondbrain.storage.repositories import TaskRepository

MAX_TASKS_PER_PAGE = 10
MAX_TASK_MESSAGE_LENGTH = 3500

TASK_LIST_TITLES = {
    "today": "Сегодня",
    "tomorrow": "Завтра",
    "week": "Неделя",
}

EMPTY_TASK_TEXTS = {
    "today": "На сегодня задач нет",
    "tomorrow": "На завтра задач нет",
    "week": "На неделе задач нет",
}


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self._repository = repository

    def build_page(self, task_list: str, page: int = 0) -> TaskPage:
        tasks = self._repository.list_tasks(task_list)
        if not tasks:
            return TaskPage(
                text=EMPTY_TASK_TEXTS[task_list],
                record_ids=(),
                page=0,
                has_previous=False,
                has_next=False,
            )

        page = max(page, 0)
        start = page * MAX_TASKS_PER_PAGE
        if start >= len(tasks):
            page = max((len(tasks) - 1) // MAX_TASKS_PER_PAGE, 0)
            start = page * MAX_TASKS_PER_PAGE

        selected = tasks[start : start + MAX_TASKS_PER_PAGE]
        lines = [TASK_LIST_TITLES[task_list]]
        record_ids: list[int] = []
        for number, task in enumerate(selected, start=1):
            flag = "✅" if task.completed else "☐"
            candidate_lines = [*lines, "", f"{number}. {flag} {task.display_text}"]
            if record_ids and len("\n".join(candidate_lines)) > MAX_TASK_MESSAGE_LENGTH:
                break
            lines = candidate_lines
            record_ids.append(task.record_id)

        end = start + len(record_ids)
        return TaskPage(
            text="\n".join(lines),
            record_ids=tuple(record_ids),
            page=page,
            has_previous=page > 0,
            has_next=end < len(tasks),
        )


def build_task_page_keyboard(task_list: str, page: TaskPage) -> InlineKeyboardMarkup:
    if not page.record_ids:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="main:open")]])

    rows = [
        [
            InlineKeyboardButton(
                str(number),
                callback_data=f"tasks:{task_list}:record:{record_id}:page:{page.page}",
            )
        ]
        for number, record_id in enumerate(page.record_ids, start=1)
    ]
    navigation: list[InlineKeyboardButton] = []
    if page.has_previous:
        navigation.append(InlineKeyboardButton("←", callback_data=f"tasks:{task_list}:page:{page.page - 1}"))
    if page.has_next:
        navigation.append(InlineKeyboardButton("→", callback_data=f"tasks:{task_list}:page:{page.page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton("Назад", callback_data="main:open")])
    return InlineKeyboardMarkup(rows)
