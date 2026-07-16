from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from secondbrain.models.records import EveningReminder
from secondbrain.storage.database import utc_now_text
from secondbrain.storage.repositories import EveningReminderRepository, InboxRepository

EVENING_REMINDER_JOB_NAME = "evening_inbox_reminder"
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
EVENING_REMINDER_TIME = time(hour=21, minute=0, tzinfo=MOSCOW_TZ)


class EveningReminderService:
    def __init__(
        self,
        *,
        reminder_repository: EveningReminderRepository,
        inbox_repository: InboxRepository,
    ) -> None:
        self._reminders = reminder_repository
        self._inbox = inbox_repository

    def prepare_due_reminder(self, now: datetime | None = None) -> EveningReminder | None:
        now = _aware_now(now)
        local_now = now.astimezone(MOSCOW_TZ)
        if local_now.time() < EVENING_REMINDER_TIME:
            return None
        return self._reminders.prepare_reminder(
            job_name=EVENING_REMINDER_JOB_NAME,
            period_key=local_now.date().isoformat(),
            started_at=utc_now_text(),
        )

    def mark_sent(
        self,
        *,
        period_key: str,
        telegram_message_id: int,
        inbox_count: int,
    ) -> None:
        self._reminders.mark_sent(
            job_name=EVENING_REMINDER_JOB_NAME,
            period_key=period_key,
            telegram_message_id=telegram_message_id,
            inbox_count=inbox_count,
            finished_at=utc_now_text(),
        )

    def mark_skipped_empty(self, *, period_key: str) -> None:
        self._reminders.mark_skipped_empty(
            job_name=EVENING_REMINDER_JOB_NAME,
            period_key=period_key,
            finished_at=utc_now_text(),
        )

    def clear_message(self, *, telegram_message_id: int) -> None:
        self._reminders.clear_message(
            job_name=EVENING_REMINDER_JOB_NAME,
            telegram_message_id=telegram_message_id,
        )

    def get_active_message_id(self) -> int | None:
        return self._reminders.get_active_message_id(job_name=EVENING_REMINDER_JOB_NAME)

    def count_inbox(self) -> int:
        return self._inbox.count_inbox()


def build_evening_reminder_text(inbox_count: int) -> str:
    return f"Во «Входящих» записей: {inbox_count}"


def build_evening_reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Разобрать", callback_data="evening_reminder:review")]]
    )


def _aware_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now
