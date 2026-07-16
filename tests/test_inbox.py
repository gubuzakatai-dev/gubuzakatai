from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, func, select

from secondbrain.services.capture import CaptureService
from secondbrain.services.inbox import (
    InboxService,
    build_inbox_keyboard,
    build_record_review_keyboard,
    build_review_routes_keyboard,
    build_tag_selection_keyboard,
    build_task_list_keyboard,
    build_trash_confirmation_keyboard,
)
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, InboxRepository
from secondbrain.storage.schema import record_tags, records, source_messages


def _services(tmp_path: Path) -> tuple[CaptureService, InboxService, Engine]:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    return CaptureService(CaptureRepository(engine)), InboxService(InboxRepository(engine)), engine


def test_empty_inbox_page_has_back_button(tmp_path: Path) -> None:
    _capture, inbox, _engine = _services(tmp_path)
    page = inbox.build_page()

    assert page.text == "Входящие пусты"
    assert page.record_ids == ()
    keyboard = build_inbox_keyboard(page)
    assert keyboard.inline_keyboard[0][0].text == "Назад"


def test_inbox_page_lists_oldest_inbox_records_first(tmp_path: Path) -> None:
    capture, inbox, _engine = _services(tmp_path)
    capture.capture_text(
        chat_id=10,
        message_id=30,
        raw_text="Поздняя мысль",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    capture.capture_text(
        chat_id=10,
        message_id=20,
        raw_text="Ранняя мысль",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    capture.capture_text(
        chat_id=10,
        message_id=21,
        raw_text="Сегодня задача",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    page = inbox.build_page()

    assert inbox.count() == 2
    assert page.text == "Входящие\n\n1. Ранняя мысль\n\n2. Поздняя мысль"
    assert len(page.record_ids) == 2


def test_inbox_page_limits_to_ten_records(tmp_path: Path) -> None:
    capture, inbox, _engine = _services(tmp_path)
    for index in range(11):
        capture.capture_text(
            chat_id=10,
            message_id=index + 1,
            raw_text=f"Мысль {index + 1}",
            telegram_sent_at=datetime(2026, 7, 16, 10, index, tzinfo=UTC),
        )

    first = inbox.build_page(0)
    second = inbox.build_page(1)

    assert len(first.record_ids) == 10
    assert first.has_next is True
    assert second.text == "Входящие\n\n1. Мысль 11"
    assert second.has_previous is True


def test_build_review_returns_selected_inbox_record_text(tmp_path: Path) -> None:
    capture, inbox, _engine = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Разобрать меня",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert inbox.build_review(captured.record_id) == "Разобрать меня"
    review_keyboard = build_record_review_keyboard(captured.record_id, page=2)
    assert review_keyboard.inline_keyboard[0][0].text == "Разобрать"
    assert review_keyboard.inline_keyboard[1][0].callback_data == "inbox:page:2"


def test_review_routes_keyboard_keeps_record_and_page_context() -> None:
    keyboard = build_review_routes_keyboard(record_id=42, page=3)

    assert keyboard.inline_keyboard[0][0].callback_data == "inbox:task:42:page:3"
    assert keyboard.inline_keyboard[1][0].callback_data == "inbox:tags:42:page:3"
    assert keyboard.inline_keyboard[2][0].callback_data == "inbox:trash:42:page:3"
    assert keyboard.inline_keyboard[3][0].callback_data == "inbox:record:42:page:3"


def test_task_list_keyboard_keeps_record_and_page_context() -> None:
    keyboard = build_task_list_keyboard(record_id=42, page=3)

    assert keyboard.inline_keyboard[0][0].callback_data == "inbox:task_list:42:today:3"
    assert keyboard.inline_keyboard[1][0].callback_data == "inbox:task_list:42:tomorrow:3"
    assert keyboard.inline_keyboard[2][0].callback_data == "inbox:task_list:42:week:3"
    assert keyboard.inline_keyboard[3][0].callback_data == "inbox:review:42:page:3"


def test_convert_inbox_record_to_task_updates_existing_record(tmp_path: Path) -> None:
    capture, inbox, engine = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сделать задачей",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert inbox.convert_to_task(record_id=captured.record_id, task_list="tomorrow") is True
    assert inbox.count() == 0

    with engine.connect() as connection:
        row = connection.execute(select(records)).one()
    assert row.id == captured.record_id
    assert row.record_type == "task"
    assert row.lifecycle_state == "task"
    assert row.task_list == "tomorrow"
    assert row.task_active_since is not None


def test_tag_selection_keyboard_marks_selected_tags(tmp_path: Path) -> None:
    _capture, inbox, _engine = _services(tmp_path)
    tags = inbox.list_tags()

    keyboard = build_tag_selection_keyboard(
        record_id=42,
        page=3,
        tags=tags[:2],
        selected_tag_ids={tags[0].tag_id},
    )

    assert keyboard.inline_keyboard[0][0].text == f"✓ {tags[0].name}"
    assert keyboard.inline_keyboard[0][0].callback_data == f"inbox:tag_toggle:42:{tags[0].tag_id}:3"
    assert keyboard.inline_keyboard[1][0].text == tags[1].name
    assert keyboard.inline_keyboard[-2][0].callback_data == "inbox:tag_save:42:3"


def test_save_tags_marks_record_processed_and_assigns_tags(tmp_path: Path) -> None:
    capture, inbox, engine = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Разобрать по тегам",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    tag_ids = tuple(tag.tag_id for tag in inbox.list_tags()[:2])

    assert inbox.save_tags(record_id=captured.record_id, tag_ids=tag_ids) is True
    assert inbox.count() == 0

    with engine.connect() as connection:
        record = connection.execute(select(records)).one()
        assigned = connection.execute(
            select(record_tags.c.tag_id).order_by(record_tags.c.tag_id)
        ).all()
    assert record.id == captured.record_id
    assert record.record_type == "thought"
    assert record.lifecycle_state == "processed"
    assert tuple(row.tag_id for row in assigned) == tuple(sorted(tag_ids))


def test_trash_confirmation_keyboard_keeps_record_and_page_context() -> None:
    keyboard = build_trash_confirmation_keyboard(record_id=42, page=3)

    assert keyboard.inline_keyboard[0][0].text == "Удалить"
    assert keyboard.inline_keyboard[0][0].callback_data == "inbox:trash_confirm:42:3"
    assert keyboard.inline_keyboard[1][0].text == "Отмена"
    assert keyboard.inline_keyboard[1][0].callback_data == "inbox:review:42:page:3"


def test_move_inbox_record_to_trash_preserves_source_and_previous_state(tmp_path: Path) -> None:
    capture, inbox, engine = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="В корзину",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert inbox.move_to_trash(record_id=captured.record_id) is True
    assert inbox.count() == 0

    with engine.connect() as connection:
        record = connection.execute(select(records)).one()
        source_count = connection.scalar(select(func.count()).select_from(source_messages))
    assert record.id == captured.record_id
    assert record.lifecycle_state == "inbox"
    assert record.trashed_at is not None
    assert record.pre_trash_lifecycle_state == "inbox"
    assert source_count == 1
