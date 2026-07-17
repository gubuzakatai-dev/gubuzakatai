from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update

from secondbrain.services.capture import CaptureService
from secondbrain.models.records import StaleTaskPrompt
from secondbrain.services.tasks import (
    TaskService,
    build_stale_task_prompt_keyboard,
    build_stale_task_prompt_text,
    build_task_page_keyboard,
)
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


def test_tomorrow_page_lists_only_tomorrow_tasks(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    earlier = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Завтра ранняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    later = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="Завтра поздняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    capture.capture_text(
        chat_id=10,
        message_id=3,
        raw_text="Сегодня не завтра",
        telegram_sent_at=datetime(2026, 7, 16, 10, 2, tzinfo=UTC),
    )

    page = tasks.build_page("tomorrow")

    assert page.record_ids == (earlier.record_id, later.record_id)
    assert page.text == "Завтра\n\n1. ☐ Ранняя\n\n2. ☐ Поздняя"
    keyboard = build_task_page_keyboard("tomorrow", page)
    assert keyboard.inline_keyboard[0][0].text == "☐ 1"
    assert keyboard.inline_keyboard[0][0].callback_data == (
        f"tasks:tomorrow:record:{earlier.record_id}:page:0"
    )
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert "➕ Добавить задачу" not in button_texts


def test_week_page_lists_only_week_tasks(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    earlier = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="На этой неделе ранняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    later = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="На этой неделе поздняя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    capture.capture_text(
        chat_id=10,
        message_id=3,
        raw_text="Завтра не неделя",
        telegram_sent_at=datetime(2026, 7, 16, 10, 2, tzinfo=UTC),
    )

    page = tasks.build_page("week")

    assert page.record_ids == (earlier.record_id, later.record_id)
    assert page.text == "Неделя\n\n1. ☐ Ранняя\n\n2. ☐ Поздняя"
    keyboard = build_task_page_keyboard("week", page)
    assert keyboard.inline_keyboard[0][0].text == "☐ 1"
    assert keyboard.inline_keyboard[0][0].callback_data == (
        f"tasks:week:record:{earlier.record_id}:page:0"
    )
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert "➕ Добавить задачу" not in button_texts


def test_tomorrow_task_can_be_added_by_text_prefix(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Завтра позвонить",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    page = tasks.build_page("tomorrow")

    assert page.record_ids == (captured.record_id,)
    assert page.text == "Завтра\n\n1. ☐ Позвонить"


def test_week_task_can_be_planned_by_text_prefix(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="На этой неделе заказать билеты",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    page = tasks.build_page("week")

    assert page.record_ids == (captured.record_id,)
    assert page.text == "Неделя\n\n1. ☐ Заказать билеты"


def test_task_moves_to_tomorrow_without_resetting_active_since(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня перенести",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.connect() as connection:
        before = connection.scalar(
            select(records.c.task_active_since).where(records.c.id == captured.record_id)
        )

    assert tasks.move_task(record_id=captured.record_id, target_task_list="tomorrow") is True

    today = tasks.build_page("today")
    tomorrow = tasks.build_page("tomorrow")
    assert today.record_ids == ()
    assert tomorrow.record_ids == (captured.record_id,)
    assert tomorrow.text == "Завтра\n\n1. ☐ Перенести"
    with engine.connect() as connection:
        row = connection.execute(
            select(records.c.task_list, records.c.task_active_since).where(
                records.c.id == captured.record_id
            )
        ).one()
    assert row.task_list == "tomorrow"
    assert row.task_active_since == before


def test_task_moves_to_week_without_resetting_active_since(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Сегодня перенести",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.connect() as connection:
        before = connection.scalar(
            select(records.c.task_active_since).where(records.c.id == captured.record_id)
        )

    assert tasks.move_task(record_id=captured.record_id, target_task_list="week") is True

    today = tasks.build_page("today")
    week = tasks.build_page("week")
    assert today.record_ids == ()
    assert week.record_ids == (captured.record_id,)
    assert week.text == "Неделя\n\n1. ☐ Перенести"
    with engine.connect() as connection:
        row = connection.execute(
            select(records.c.task_list, records.c.task_active_since).where(
                records.c.id == captured.record_id
            )
        ).one()
    assert row.task_list == "week"
    assert row.task_active_since == before


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


def test_toggle_tomorrow_task_completion_sets_and_clears_completed_at(tmp_path: Path) -> None:
    capture, tasks = _services(tmp_path)
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Завтра сделать",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )

    assert tasks.toggle_completion(record_id=captured.record_id, task_list="tomorrow") is True
    completed_page = tasks.build_page("tomorrow")
    assert completed_page.text == "Завтра\n\n1. ✅ Сделать"
    completed_keyboard = build_task_page_keyboard("tomorrow", completed_page)
    assert completed_keyboard.inline_keyboard[0][0].text == "✅ 1"

    assert tasks.toggle_completion(record_id=captured.record_id, task_list="tomorrow") is True
    active_page = tasks.build_page("tomorrow")
    assert active_page.text == "Завтра\n\n1. ☐ Сделать"
    active_keyboard = build_task_page_keyboard("tomorrow", active_page)
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


def test_daily_rollover_moves_active_tomorrow_tasks_to_today(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    active = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Завтра активная",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    done = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="Завтра выполненная",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    with engine.begin() as connection:
        before = connection.scalar(
            select(records.c.task_active_since).where(records.c.id == active.record_id)
        )
        connection.execute(
            update(records)
            .where(records.c.id == done.record_id)
            .values(completed_at="2026-07-16T20:59:00+00:00")
        )

    changed_count = tasks.process_today_rollover(
        now=datetime(2026, 7, 16, 21, 5, tzinfo=UTC),
    )

    assert changed_count == 2
    today = tasks.build_page("today")
    tomorrow = tasks.build_page("tomorrow")
    assert today.record_ids == (active.record_id,)
    assert today.text == "Сегодня\n\n1. ☐ Активная"
    assert tomorrow.record_ids == ()
    with engine.connect() as connection:
        active_row = connection.execute(
            select(records.c.task_list, records.c.task_active_since).where(
                records.c.id == active.record_id
            )
        ).one()
        done_row = connection.execute(
            select(records.c.task_list, records.c.hidden_at).where(records.c.id == done.record_id)
        ).one()
    assert active_row.task_list == "today"
    assert active_row.task_active_since == before
    assert done_row.task_list == "tomorrow"
    assert done_row.hidden_at is not None


def test_resume_hidden_task_returns_it_to_selected_list(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Hidden task",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(
                record_type="task",
                lifecycle_state="task",
                task_list="today",
                task_active_since="2026-07-16T10:00:00+00:00",
                completed_at="2026-07-16T20:59:00+00:00",
                hidden_at="2026-07-16T21:05:00+00:00",
                stale_prompted_at="2026-07-16T20:00:00+00:00",
                stale_prompt_message_id=123,
            )
        )

    assert tasks.resume_task(record_id=captured.record_id, target_task_list="week") is True

    page = tasks.build_page("week")
    assert page.record_ids == (captured.record_id,)
    with engine.connect() as connection:
        row = connection.execute(
            select(
                records.c.task_list,
                records.c.completed_at,
                records.c.hidden_at,
                records.c.stale_prompted_at,
                records.c.stale_prompt_message_id,
                records.c.task_active_since,
            ).where(records.c.id == captured.record_id)
        ).one()
    assert row.task_list == "week"
    assert row.completed_at is None
    assert row.hidden_at is None
    assert row.stale_prompted_at is None
    assert row.stale_prompt_message_id is None
    assert row.task_active_since is not None


def test_prepare_stale_task_prompt_selects_oldest_unprompted_active_task(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    fresh = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Fresh",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    old_prompted = capture.capture_text(
        chat_id=10,
        message_id=2,
        raw_text="Old prompted",
        telegram_sent_at=datetime(2026, 7, 16, 10, 1, tzinfo=UTC),
    )
    old_done = capture.capture_text(
        chat_id=10,
        message_id=3,
        raw_text="Old done",
        telegram_sent_at=datetime(2026, 7, 16, 10, 2, tzinfo=UTC),
    )
    oldest = capture.capture_text(
        chat_id=10,
        message_id=4,
        raw_text="Oldest active",
        telegram_sent_at=datetime(2026, 7, 16, 10, 3, tzinfo=UTC),
    )
    old_active = capture.capture_text(
        chat_id=10,
        message_id=5,
        raw_text="Old active",
        telegram_sent_at=datetime(2026, 7, 16, 10, 4, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id.in_([fresh.record_id, old_prompted.record_id, old_done.record_id, oldest.record_id, old_active.record_id]))
            .values(record_type="task", lifecycle_state="task", task_list="today")
        )
        connection.execute(
            update(records)
            .where(records.c.id == fresh.record_id)
            .values(task_active_since="2026-07-08T21:30:00+00:00")
        )
        connection.execute(
            update(records)
            .where(records.c.id == old_prompted.record_id)
            .values(
                task_active_since="2026-07-01T21:30:00+00:00",
                stale_prompted_at="2026-07-10T21:00:00+00:00",
            )
        )
        connection.execute(
            update(records)
            .where(records.c.id == old_done.record_id)
            .values(
                task_active_since="2026-07-01T21:30:00+00:00",
                completed_at="2026-07-10T21:00:00+00:00",
            )
        )
        connection.execute(
            update(records)
            .where(records.c.id == oldest.record_id)
            .values(task_active_since="2026-07-01T21:30:00+00:00", task_list="tomorrow")
        )
        connection.execute(
            update(records)
            .where(records.c.id == old_active.record_id)
            .values(task_active_since="2026-07-02T21:30:00+00:00", task_list="week")
        )

    prompt = tasks.prepare_stale_task_prompt(now=datetime(2026, 7, 10, 21, 1, tzinfo=UTC))

    assert prompt is not None
    assert prompt.record_id == oldest.record_id
    assert prompt.display_text == "Oldest active"
    assert prompt.task_list == "tomorrow"
    with engine.connect() as connection:
        prompted_at = connection.scalar(
            select(records.c.stale_prompted_at).where(records.c.id == oldest.record_id)
        )
    assert prompted_at is not None


def test_stale_task_prompt_keyboard_has_available_actions() -> None:
    prompt = StaleTaskPrompt(record_id=42, display_text="Old task", task_list="week")

    text = build_stale_task_prompt_text(prompt)
    keyboard = build_stale_task_prompt_keyboard(prompt.record_id)

    assert "Old task" in text
    assert keyboard.inline_keyboard[0][0].callback_data == "stale:move:42:today"
    assert keyboard.inline_keyboard[1][0].callback_data == "stale:move:42:tomorrow"
    assert keyboard.inline_keyboard[2][0].callback_data == "stale:move:42:week"
    assert keyboard.inline_keyboard[3][0].callback_data == "stale:done:42"
    assert keyboard.inline_keyboard[4][0].callback_data == "stale:trash:42"


def test_move_stale_task_changes_list_and_clears_prompt_message(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Old task",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(
                record_type="task",
                lifecycle_state="task",
                task_list="week",
                task_active_since="2026-07-01T21:30:00+00:00",
                stale_prompted_at="2026-07-10T21:01:00+00:00",
                stale_prompt_message_id=123,
            )
        )

    assert tasks.move_stale_task(record_id=captured.record_id, target_task_list="today") is True

    with engine.connect() as connection:
        row = connection.execute(
            select(records.c.task_list, records.c.task_active_since, records.c.stale_prompted_at, records.c.stale_prompt_message_id)
            .where(records.c.id == captured.record_id)
        ).one()
    assert row.task_list == "today"
    assert row.task_active_since == "2026-07-01T21:30:00+00:00"
    assert row.stale_prompted_at == "2026-07-10T21:01:00+00:00"
    assert row.stale_prompt_message_id is None


def test_complete_stale_task_marks_done_and_clears_prompt_message(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Old task",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(
                record_type="task",
                lifecycle_state="task",
                task_list="today",
                task_active_since="2026-07-01T21:30:00+00:00",
                stale_prompted_at="2026-07-10T21:01:00+00:00",
                stale_prompt_message_id=123,
            )
        )

    assert tasks.complete_stale_task(record_id=captured.record_id) is True

    with engine.connect() as connection:
        row = connection.execute(
            select(records.c.completed_at, records.c.stale_prompt_message_id)
            .where(records.c.id == captured.record_id)
        ).one()
    assert row.completed_at is not None
    assert row.stale_prompt_message_id is None


def test_move_stale_task_to_trash_preserves_previous_state(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "test.sqlite3")
    initialize_database(engine)
    capture = CaptureService(CaptureRepository(engine))
    tasks = TaskService(TaskRepository(engine))
    captured = capture.capture_text(
        chat_id=10,
        message_id=1,
        raw_text="Old task",
        telegram_sent_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
    )
    with engine.begin() as connection:
        connection.execute(
            update(records)
            .where(records.c.id == captured.record_id)
            .values(
                record_type="task",
                lifecycle_state="task",
                task_list="tomorrow",
                task_active_since="2026-07-01T21:30:00+00:00",
                stale_prompted_at="2026-07-10T21:01:00+00:00",
                stale_prompt_message_id=123,
            )
        )

    assert tasks.move_stale_task_to_trash(record_id=captured.record_id) is True

    with engine.connect() as connection:
        row = connection.execute(
            select(
                records.c.trashed_at,
                records.c.pre_trash_lifecycle_state,
                records.c.pre_trash_task_list,
                records.c.stale_prompt_message_id,
            ).where(records.c.id == captured.record_id)
        ).one()
    assert row.trashed_at is not None
    assert row.pre_trash_lifecycle_state == "task"
    assert row.pre_trash_task_list == "tomorrow"
    assert row.stale_prompt_message_id is None
