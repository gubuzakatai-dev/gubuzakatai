from pathlib import Path

from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.schema import records, tags


def test_initialize_database_seeds_tags_once(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    initialize_database(engine)

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(tags)) == 10


def test_deleted_initial_tags_are_not_recreated(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    with engine.begin() as connection:
        connection.execute(tags.delete())

    initialize_database(engine)

    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(tags)) == 0


def test_records_reject_invalid_task_state(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)

    with engine.begin() as connection:
        try:
            connection.execute(
                insert(records).values(
                    display_text="Ошибка",
                    record_type="thought",
                    lifecycle_state="inbox",
                    task_list="today",
                    created_at="2026-07-16T00:00:00+00:00",
                    updated_at="2026-07-16T00:00:00+00:00",
                )
            )
        except IntegrityError:
            return
    raise AssertionError("SQLite accepted an invalid thought task_list")
