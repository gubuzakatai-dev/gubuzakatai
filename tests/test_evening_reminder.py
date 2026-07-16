from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from secondbrain.services.capture import CaptureService
from secondbrain.services.evening_reminder import (
    EVENING_REMINDER_JOB_NAME,
    EveningReminderService,
    build_evening_reminder_keyboard,
    build_evening_reminder_text,
)
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import (
    CaptureRepository,
    EveningReminderRepository,
    InboxRepository,
)
from secondbrain.storage.schema import scheduled_runs


def _services(tmp_path: Path) -> tuple[CaptureService, EveningReminderService]:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    inbox_repository = InboxRepository(engine)
    return (
        CaptureService(CaptureRepository(engine)),
        EveningReminderService(
            reminder_repository=EveningReminderRepository(engine),
            inbox_repository=inbox_repository,
        ),
    )


def test_evening_reminder_is_not_due_before_nine_pm(tmp_path: Path) -> None:
    _capture, reminders = _services(tmp_path)

    reminder = reminders.prepare_due_reminder(
        datetime(2026, 7, 16, 17, 59, tzinfo=UTC),
    )

    assert reminder is None


def test_evening_reminder_is_sent_once_per_moscow_date(tmp_path: Path) -> None:
    capture, reminders = _services(tmp_path)
    capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Входящая мысль",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    first = reminders.prepare_due_reminder(datetime(2026, 7, 16, 18, 0, tzinfo=UTC))
    assert first is not None
    assert first.period_key == "2026-07-16"
    assert first.inbox_count == 1

    reminders.mark_sent(
        period_key=first.period_key,
        telegram_message_id=100,
        inbox_count=first.inbox_count,
    )

    assert reminders.prepare_due_reminder(datetime(2026, 7, 16, 18, 1, tzinfo=UTC)) is None


def test_evening_reminder_skips_empty_inbox(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    reminders = EveningReminderService(
        reminder_repository=EveningReminderRepository(engine),
        inbox_repository=InboxRepository(engine),
    )

    reminder = reminders.prepare_due_reminder(datetime(2026, 7, 16, 18, 0, tzinfo=UTC))
    assert reminder is not None
    assert reminder.inbox_count == 0

    reminders.mark_skipped_empty(period_key=reminder.period_key)

    with engine.connect() as connection:
        row = connection.execute(select(scheduled_runs)).one()
    assert row.job_name == EVENING_REMINDER_JOB_NAME
    assert row.status == "succeeded"
    assert row.telegram_message_id is None


def test_evening_reminder_does_not_duplicate_running_check(tmp_path: Path) -> None:
    capture, reminders = _services(tmp_path)
    capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Не дублировать",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    first = reminders.prepare_due_reminder(datetime(2026, 7, 16, 18, 0, tzinfo=UTC))
    second = reminders.prepare_due_reminder(datetime(2026, 7, 16, 18, 1, tzinfo=UTC))

    assert first is not None
    assert second is None


def test_evening_reminder_message_has_count_and_single_review_button() -> None:
    keyboard = build_evening_reminder_keyboard()

    assert build_evening_reminder_text(3) == "Во «Входящих» записей: 3"
    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].text == "Разобрать"
    assert keyboard.inline_keyboard[0][0].callback_data == "evening_reminder:review"
