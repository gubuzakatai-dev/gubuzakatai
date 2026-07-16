from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import update

from secondbrain.services.capture import CaptureService
from secondbrain.services.tasks import TaskService, build_task_page_keyboard
from secondbrain.storage.database import create_database_engine, initialize_database
from secondbrain.storage.repositories import CaptureRepository, TaskRepository
from secondbrain.storage.schema import records


def _services(tmp_path: Path) -> tuple[CaptureService, TaskService]:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    return CaptureService(CaptureRepository(engine)), TaskService(TaskRepository(engine))


def test_empty_today_page_has_back_button(tmp_path: Path) -> None:
    _capture, tasks = _services(tmp_path)
    page = tasks.build_page("today")

    assert page.text == "На сегодня задач нет"
    assert page.record_ids == ()
    keyboard = build_task_page_keyboard("today", page)
    assert keyboard.inline_keyboard[0][0].text == "Назад"
    assert keyboard.inline_keyboard[0][0].callback_data == "main:open"


def test_today_page_lists_oldest_today_tasks_first(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    earlier = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня ранняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    later = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="Сегодня поздняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    capture.capture_text(
        chat_id=10,
        message_id=3,
        raw_text="Завтра не сегодня",
        telegram_sent_at=datetime(2026, 7, 16, 10, 2, tzinfo=UTC),
    )

    page = tasks.build_page("today")

    assert page.record_ids == (earlier.record_id, later.record_id)
    assert page.text == "Сегодня\n\n1. ☐ Ранняя\n\n2. ☐ Поздняя"
    keyboard = build_task_page_keyboard("today", page)
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert "➕ Добавить задачу" not in button_texts


def test_today_page_shows_completed_flag(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня готово",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(completed_at="2026-07-16T10:01:00+00:00")
        )

    page = tasks.build_page("today")

    assert page.text == "Сегодня\n\n1. ✅ Готово"


def test_today_page_limits_to_ten_tasks(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    for index in range(11):
        capture.capture_text(
            chat_id=10,
            message_id=index + 1,
            raw_text=f"Сегодня задача {index + 1}",
            telegram_sent_at=datetime(2026, 7, 16, 10, index, tzinfo=UTC),
        )

    first = tasks.build_page("today")
    second = tasks.build_page("today", 1)

    assert len(first.record_ids) == 10
    assert first.has_next is True
    assert second.text == "Сегодня\n\n1. ☐ Задача 11"
    assert second.has_previous is True
    keyboard = build_task_page_keyboard("today", first)
    assert keyboard.inline_keyboard[-2][0].callback_data == "tasks:today:page:1"


def test_toggle_today_task_completion_sets_and_clears_completed_at(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня сделать",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert tasks.toggle_completion(record_id=captured.record_id, task_list="today") is True
    completed_page = tasks.build_page("today")
    assert completed_page.text == "Сегодня\n\n1. ✅ Сделать"
    completed_keyboard = build_task_page_keyboard("today", completed_page)
    assert completed_keyboard.inline_keyboard[0][0].text == "✅ 1"
    assert completed_keyboard.inline_keyboard[0][0].callback_data == (
        f"tasks:today:record:{captured.record_id}:page:0"
    )

    assert tasks.toggle_completion(record_id=captured.record_id, task_list="today") is True
    active_page = tasks.build_page("today")
    assert active_page.text == "Сегодня\n\n1. ☐ Сделать"
    active_keyboard = build_task_page_keyboard("today", active_page)
    assert active_keyboard.inline_keyboard[0][0].text == "☐ 1"


def test_toggle_completion_ignores_other_task_list(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня сделать",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert tasks.toggle_completion(record_id=captured.record_id, task_list="tomorrow") is False

    page = tasks.build_page("today")
    assert page.text == "Сегодня\n\n1. ☐ Сделать"


def test_today_rollover_hides_only_completed_tasks_before_cutoff(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    old_done = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня старая выполненная",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    active = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="Сегодня активная",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    fresh_done = capture.capture_text(
        chat_id=10,
        message_id=3,
        raw_text="Сегодня свежая выполненная",
        telegram_sent_at=datetime(2026, 7, 16, 10, 2, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == old_done.record_id)
            .values(completed_at="2026-07-16T20:59:00+00:00")
        )
        connection.execute(
            update(records)
            .where(records.c.id == fresh_done.record_id)
            .values(completed_at="2026-07-16T21:01:00+00:00")
        )

    hidden_count = tasks.process_today_rollover(
        now=datetime(2026, 7, 16, 21, 5, tzinfo=UTC),
    )

    assert hidden_count == 1
    page = tasks.build_page("today")
    assert page.record_ids == (active.record_id, fresh_done.record_id)
    assert page.text == "Сегодня\n\n1. ☐ Активная\n\n2. ✅ Свежая выполненная"
    assert tasks.process_today_rollover(now=datetime(2026, 7, 16, 21, 6, tzinfo=UTC)) is None
