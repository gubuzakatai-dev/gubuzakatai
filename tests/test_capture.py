from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from secondbrain.services.capture import CaptureService, detect_standalone_link, parse_text
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository
from secondbrain.storage.schema import processing_results, records, source_messages


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


def test_standalone_link_creates_pending_metadata_result(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))
    sent_at = datetime(2026, 7, 16, tzinfo=UTC)

    captured = service.capture_text(
        chat_id=10,
        message_id=22,
        raw_text="https://example.com/page",
        telegram_sent_at=sent_at,
    )

    assert captured.display_text == "https://example.com/page"
    assert captured.destination == "Входящие"
    with engine.connect() as connection:
        result = connection.execute(select(processing_results)).one()
        assert result.operation == "link_metadata"
        assert result.status == "pending"
        assert result.input_text == "https://example.com/page"
        assert result.attempt_no == 1


def test_link_inside_text_does_not_create_metadata_result(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))
    sent_at = datetime(2026, 7, 16, tzinfo=UTC)

    service.capture_text(
        chat_id=10,
        message_id=23,
        raw_text="почитать https://example.com/page",
        telegram_sent_at=sent_at,
    )

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(processing_results)) == 0


def test_detect_standalone_link_rejects_unsafe_urls() -> None:
    assert detect_standalone_link("ftp://example.com") is None
    assert detect_standalone_link("https://user:pass@example.com") is None
    assert detect_standalone_link("http://localhost") is None
    assert detect_standalone_link("http://127.0.0.1") is None
    assert detect_standalone_link("http://10.0.0.1") is None


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


def test_unconfirmed_confirmations_are_ordered_by_sent_time_then_message_id(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    service = CaptureService(CaptureRepository(engine))

    service.capture_text(
        chat_id=10,
        message_id=30,
        raw_text="Позже",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    service.capture_text(
        chat_id=10,
        message_id=20,
        raw_text="Раньше",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    service.capture_text(
        chat_id=10,
        message_id=21,
        raw_text="Следом",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    first = service.get_next_unconfirmed(chat_id=10)
    assert first is not None
    assert first.display_text == "Раньше"
    service.mark_confirmation_sent(source_message_id=first.source_message_id)

    second = service.get_next_unconfirmed(chat_id=10)
    assert second is not None
    assert second.display_text == "Следом"
    service.mark_confirmation_sent(source_message_id=second.source_message_id)

    third = service.get_next_unconfirmed(chat_id=10)
    assert third is not None
    assert third.display_text == "Позже"
