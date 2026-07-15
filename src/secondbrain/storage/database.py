from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, insert, inspect
from sqlalchemy.engine import Connection

from secondbrain.storage.schema import metadata, tags

INITIAL_TAGS = (
    "Однажды",
    "Купить",
    "Поездки",
    "Рукоделие",
    "Смотреть",
    "Играть",
    "Читать",
    "ИИ",
    "Здоровье",
    "Прочее",
)


def utc_now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def normalize_tag_name(name: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize("NFC", name.strip())
    return " ".join(normalized.split()).casefold()


def create_database_engine(path: Path) -> Engine:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def initialize_database(engine: Engine) -> None:
    """Create the schema and seed tags only during first database creation."""
    is_new_database = not inspect(engine).has_table("tags")
    metadata.create_all(engine)
    if is_new_database:
        with engine.begin() as connection:
            _insert_initial_tags(connection)


def _insert_initial_tags(connection: Connection) -> None:
    now = utc_now_text()
    connection.execute(
        insert(tags),
        [
            {
                "name": name,
                "normalized_name": normalize_tag_name(name),
                "is_system": True,
                "sort_order": position,
                "created_at": now,
                "updated_at": now,
            }
            for position, name in enumerate(INITIAL_TAGS, start=1)
        ],
    )


@contextmanager
def transaction(engine: Engine) -> Iterator[Connection]:
    with engine.begin() as connection:
        yield connection
