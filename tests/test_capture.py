from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from secondbrain.services.capture import CaptureService, parse_text
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository
from secondbrain.storage.schema import records, source_messages


def test_parse_text_routes_explicit_prefixes() -> None:
    assert parse_text("Сегодня купить хлеб") == ("Купить хлеб", "today")
    assert parse_text("зАвТрА: позвонить") == ("Позвонить", "tomorrow")
    assert parse_text("На этой неделе — заказать билеты") == ("Заказать билеты", "week")


def test_parse_text_keeps_non_prefix_text_unchanged() -> None:
    text = "Купить сегодня хлеб  "
    assert parse_text(text) == (text, None)
    assert parse_text("Сегодняшняя встреча") == ("Сегодняшняя встреча", None)


def test_capture_is_atomic_and_idempotent(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))
    sent_at = datetime(2026, 7, 16, tzinfo=UTC)

    first = service.capture_text(
        chat_id=10, message_id=20, raw_text="Сегодня дело", telegram_sent_at=sent_at
    )
    second = service.capture_text(
        chat_id=10, message_id=20, raw_text="Сегодня дело", telegram_sent_at=sent_at
    )

    assert first.record_id == second.record_id
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(records)) == 1
        assert connection.scalar(select(func.count()).select_from(source_messages)) == 1
        source = connection.execute(select(source_messages)).one()
        assert source.raw_text == "Сегодня дело"


def test_keyboard_dictation_text_uses_regular_text_route(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))
    sent_at = datetime(2026, 7, 16, tzinfo=UTC)

    captured = service.capture_text(
        chat_id=10,
        message_id=21,
        raw_text="На этой неделе забрать документы",
        telegram_sent_at=sent_at,
    )

    assert captured.display_text == "Забрать документы"
    assert captured.destination == "Неделя"
    with engine.connect() as connection:
        source = connection.execute(select(source_messages)).one()
        assert source.raw_text == "На этой неделе забрать документы"


def test_confirmed_duplicate_needs_no_second_reply(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))
    sent_at = datetime(2026, 7, 16, tzinfo=UTC)
    service.capture_text(chat_id=10, message_id=20, raw_text="Мысль", telegram_sent_at=sent_at)
    service.mark_confirmed(chat_id=10, message_id=20)

    duplicate = service.capture_text(
        chat_id=10, message_id=20, raw_text="Мысль", telegram_sent_at=sent_at
    )

    assert duplicate.confirmation_required is False
