from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from secondbrain.services.capture import CaptureService
from secondbrain.services.link_metadata import (
    FetchedHtml,
    LinkMetadataError,
    LinkMetadataService,
    parse_html_metadata,
)
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, LinkMetadataRepository
from secondbrain.storage.schema import processing_results, records


class FakeFetcher:
    def __init__(self, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self._body = body
        self._content_type = content_type
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchedHtml:
        self.urls.append(url)
        return FetchedHtml(body=self._body, content_type=self._content_type)


class FailingFetcher:
    def __init__(self, code: str) -> None:
        self._code = code

    def fetch(self, url: str) -> FetchedHtml:
        raise LinkMetadataError(self._code, f"failed for {url}")


def test_parse_html_metadata_extracts_title_and_description() -> None:
    metadata = parse_html_metadata(
        b"""
        <html>
          <head>
            <title> Example &amp; Page </title>
            <meta name="description" content=" Short  summary ">
          </head>
        </html>
        """
    )

    assert metadata.title == "Example & Page"
    assert metadata.description == "Short summary"


def test_process_next_saves_metadata_and_enriches_unchanged_display_text(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    capture.capture_text(
        chat_id=10,
        message_id=30,
        raw_text="https://example.com/page",
        telegram_sent_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    fetcher = FakeFetcher(
        b"<title>Example</title><meta name='description' content='Readable page'>"
    )
    service = LinkMetadataService(LinkMetadataRepository(engine), fetcher=fetcher)

    assert service.process_next() is True

    with engine.connect() as connection:
        record = connection.execute(select(records)).one()
        result = connection.execute(select(processing_results)).one()
    assert fetcher.urls == ["https://example.com/page"]
    assert record.display_text == (
        "https://example.com/page\nНазвание: Example\nОписание: Readable page"
    )
    assert result.status == "succeeded"
    assert result.output_text == record.display_text
    assert '"title": "Example"' in result.output_json


def test_process_next_keeps_user_edited_display_text(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=31,
        raw_text="https://example.com/page",
        telegram_sent_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(display_text="ручная правка")
        )
    fetcher = FakeFetcher(b"<title>Example</title>")
    service = LinkMetadataService(LinkMetadataRepository(engine), fetcher=fetcher)

    assert service.process_next() is True

    with engine.connect() as connection:
        record = connection.execute(select(records)).one()
        result = connection.execute(select(processing_results)).one()
    assert record.display_text == "ручная правка"
    assert result.status == "succeeded"
    assert result.output_text == "https://example.com/page\nНазвание: Example"


def test_temporary_error_creates_next_pending_attempt(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    capture.capture_text(
        chat_id=10,
        message_id=32,
        raw_text="https://example.com/page",
        telegram_sent_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    service = LinkMetadataService(
        LinkMetadataRepository(engine),
        fetcher=FailingFetcher("temporary_network_error"),
    )

    assert service.process_next() is True

    with engine.connect() as connection:
        rows = connection.execute(
            select(processing_results).order_by(processing_results.c.attempt_no)
        ).all()
    assert [row.status for row in rows] == ["failed", "pending"]
    assert [row.attempt_no for row in rows] == [1, 2]


def test_permanent_error_does_not_create_retry(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    capture.capture_text(
        chat_id=10,
        message_id=33,
        raw_text="https://example.com/page",
        telegram_sent_at=datetime(2026, 7, 16, tzinfo=UTC),
    )
    service = LinkMetadataService(
        LinkMetadataRepository(engine),
        fetcher=FailingFetcher("unsupported_content_type"),
    )

    assert service.process_next() is True

    with engine.connect() as connection:
        rows = connection.execute(select(processing_results)).all()
    assert len(rows) == 1
    assert rows[0].status == "failed"
