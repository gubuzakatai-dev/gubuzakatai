from datetime import UTC, datetime
from pathlib import Path

from secondbrain.services.capture import CaptureService
from secondbrain.services.inbox import InboxService, build_inbox_keyboard
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, InboxRepository


def _services(tmp_path: Path) -> tuple[CaptureService, InboxService]:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    return CaptureService(CaptureRepository(engine)), InboxService(InboxRepository(engine))


def test_empty_inbox_page_has_back_button(tmp_path: Path) -> None:
    _capture, inbox = _services(tmp_path)
    page = inbox.build_page()

    assert page.text == "Входящие пусты"
    assert page.record_ids == ()
    keyboard = build_inbox_keyboard(page)
    assert keyboard.inline_keyboard[0][0].text == "Назад"


def test_inbox_page_lists_oldest_inbox_records_first(tmp_path: Path) -> None:
    capture, inbox = _services(tmp_path)
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
    capture, inbox = _services(tmp_path)
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
