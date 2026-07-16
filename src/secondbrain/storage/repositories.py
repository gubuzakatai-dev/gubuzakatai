import json
from dataclasses import dataclass

from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from secondbrain.models.records import (
    CapturedRecord,
    InboxRecord,
    PendingConfirmation,
    EveningReminder,
    ProcessedRecord,
    ReviewRecord,
    TagOption,
    TaskRecord,
)
from secondbrain.storage.database import transaction
from secondbrain.storage.schema import (
    processing_results,
    record_tags,
    records,
    scheduled_runs,
    source_messages,
    tags,
)


class CaptureRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        *,
        chat_id: int,
        message_id: int,
        raw_text: str,
        display_text: str,
        record_type: str,
        lifecycle_state: str,
        task_list: str | None,
        link_metadata_url: str | None,
        telegram_sent_at: str,
        received_at: str,
    ) -> CapturedRecord:
        try:
            with transaction(self._engine) as connection:
                created = connection.execute(
                    insert(records).values(
                        display_text=display_text,
                        record_type=record_type,
                        lifecycle_state=lifecycle_state,
                        task_list=task_list,
                        task_active_since=received_at if record_type == "task" else None,
                        created_at=received_at,
                        updated_at=received_at,
                    )
                )
                record_id = int(created.inserted_primary_key[0])
                source = connection.execute(
                    insert(source_messages).values(
                        record_id=record_id,
                        telegram_chat_id=chat_id,
                        telegram_message_id=message_id,
                        raw_text=raw_text,
                        telegram_sent_at=telegram_sent_at,
                        received_at=received_at,
                        created_at=received_at,
                    )
                )
                if link_metadata_url is not None:
                    connection.execute(
                        insert(processing_results).values(
                            record_id=record_id,
                            source_message_id=int(source.inserted_primary_key[0]),
                            operation="link_metadata",
                            status="pending",
                            input_text=link_metadata_url,
                            attempt_no=1,
                            created_at=received_at,
                        )
                    )
            return CapturedRecord(record_id, display_text, _destination(task_list), True)
        except IntegrityError:
            return self._get_existing(chat_id=chat_id, message_id=message_id)

    def mark_confirmed(self, *, chat_id: int, message_id: int, confirmed_at: str) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(source_messages)
                .where(
                    source_messages.c.telegram_chat_id == chat_id,
                    source_messages.c.telegram_message_id == message_id,
                    source_messages.c.confirmation_sent_at.is_(None),
                )
                .values(confirmation_sent_at=confirmed_at)
            )

    def get_next_unconfirmed(self, *, chat_id: int) -> PendingConfirmation | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    source_messages.c.id,
                    source_messages.c.telegram_chat_id,
                    records.c.id.label("record_id"),
                    records.c.display_text,
                    records.c.task_list,
                )
                .join(records, records.c.id == source_messages.c.record_id)
                .where(
                    source_messages.c.telegram_chat_id == chat_id,
                    source_messages.c.confirmation_sent_at.is_(None),
                )
                .order_by(
                    source_messages.c.telegram_sent_at,
                    source_messages.c.telegram_message_id,
                )
                .limit(1)
            ).one_or_none()
        if row is None:
            return None
        return PendingConfirmation(
            source_message_id=row.id,
            chat_id=row.telegram_chat_id,
            record_id=row.record_id,
            display_text=row.display_text,
            destination=_destination(row.task_list),
        )

    def mark_confirmed_by_source_id(self, *, source_message_id: int, confirmed_at: str) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(source_messages)
                .where(
                    source_messages.c.id == source_message_id,
                    source_messages.c.confirmation_sent_at.is_(None),
                )
                .values(confirmation_sent_at=confirmed_at)
            )

    def _get_existing(self, *, chat_id: int, message_id: int) -> CapturedRecord:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    records.c.id,
                    records.c.display_text,
                    records.c.task_list,
                    source_messages.c.confirmation_sent_at,
                )
                .join(source_messages, source_messages.c.record_id == records.c.id)
                .where(
                    source_messages.c.telegram_chat_id == chat_id,
                    source_messages.c.telegram_message_id == message_id,
                )
            ).one()
        return CapturedRecord(
            record_id=row.id,
            display_text=row.display_text,
            destination=_destination(row.task_list),
            confirmation_required=row.confirmation_sent_at is None,
        )


def _destination(task_list: str | None) -> str:
    return {
        "today": "Сегодня",
        "tomorrow": "Завтра",
        "week": "Неделя",
        None: "Входящие",
    }[task_list]


@dataclass(frozen=True, slots=True)
class PendingLinkMetadata:
    result_id: int
    record_id: int
    source_message_id: int | None
    url: str
    current_display_text: str
    attempt_no: int


class LinkMetadataRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_next_pending(self) -> PendingLinkMetadata | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    processing_results.c.id,
                    processing_results.c.record_id,
                    processing_results.c.source_message_id,
                    processing_results.c.input_text,
                    processing_results.c.attempt_no,
                    records.c.display_text,
                )
                .join(records, records.c.id == processing_results.c.record_id)
                .where(
                    processing_results.c.operation == "link_metadata",
                    processing_results.c.status == "pending",
                )
                .order_by(processing_results.c.created_at, processing_results.c.id)
                .limit(1)
            ).one_or_none()
        if row is None:
            return None
        return PendingLinkMetadata(
            result_id=row.id,
            record_id=row.record_id,
            source_message_id=row.source_message_id,
            url=row.input_text,
            current_display_text=row.display_text,
            attempt_no=row.attempt_no,
        )

    def mark_running(self, *, result_id: int, started_at: str) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(processing_results)
                .where(
                    processing_results.c.id == result_id,
                    processing_results.c.status == "pending",
                )
                .values(status="running", started_at=started_at)
            )

    def mark_succeeded(
        self,
        *,
        pending: PendingLinkMetadata,
        title: str | None,
        description: str | None,
        finished_at: str,
    ) -> None:
        enriched_text = format_link_display(pending.url, title=title, description=description)
        output = {"url": pending.url, "title": title, "description": description}
        with transaction(self._engine) as connection:
            connection.execute(
                update(processing_results)
                .where(processing_results.c.id == pending.result_id)
                .values(
                    status="succeeded",
                    output_text=enriched_text,
                    output_json=json.dumps(output, ensure_ascii=False, sort_keys=True),
                    error_code=None,
                    error_message=None,
                    finished_at=finished_at,
                )
            )
            connection.execute(
                update(records)
                .where(
                    records.c.id == pending.record_id,
                    records.c.display_text == pending.url,
                )
                .values(display_text=enriched_text, updated_at=finished_at)
            )

    def mark_failed(
        self,
        *,
        pending: PendingLinkMetadata,
        error_code: str,
        error_message: str,
        finished_at: str,
        retry: bool,
    ) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(processing_results)
                .where(processing_results.c.id == pending.result_id)
                .values(
                    status="failed",
                    error_code=error_code,
                    error_message=error_message,
                    finished_at=finished_at,
                )
            )
            if retry:
                connection.execute(
                    insert(processing_results).values(
                        record_id=pending.record_id,
                        source_message_id=pending.source_message_id,
                        operation="link_metadata",
                        status="pending",
                        input_text=pending.url,
                        attempt_no=pending.attempt_no + 1,
                        created_at=finished_at,
                    )
                )


def format_link_display(url: str, *, title: str | None, description: str | None) -> str:
    lines = [url]
    if title:
        lines.append(f"Название: {title}")
    if description:
        lines.append(f"Описание: {description}")
    return "\n".join(lines)


class InboxRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_inbox(self) -> list[InboxRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(records.c.id, records.c.display_text)
                .join(source_messages, source_messages.c.record_id == records.c.id)
                .where(
                    records.c.lifecycle_state == "inbox",
                    records.c.trashed_at.is_(None),
                )
                .order_by(
                    source_messages.c.telegram_sent_at,
                    source_messages.c.telegram_message_id,
                    records.c.id,
                )
            ).all()
        return [
            InboxRecord(record_id=row.id, display_text=row.display_text)
            for row in rows
        ]

    def count_inbox(self) -> int:
        with self._engine.connect() as connection:
            return int(
                connection.scalar(
                    select(func.count())
                    .select_from(records)
                    .where(
                        records.c.lifecycle_state == "inbox",
                        records.c.trashed_at.is_(None),
                    )
                )
                or 0
            )

    def get_inbox_record(self, record_id: int) -> ReviewRecord | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(records.c.id, records.c.display_text).where(
                    records.c.id == record_id,
                    records.c.lifecycle_state == "inbox",
                    records.c.trashed_at.is_(None),
                )
            ).one_or_none()
        if row is None:
            return None
        return ReviewRecord(record_id=row.id, display_text=row.display_text)

    def convert_inbox_to_task(self, *, record_id: int, task_list: str, changed_at: str) -> bool:
        with transaction(self._engine) as connection:
            result = connection.execute(
                update(records)
                .where(
                    records.c.id == record_id,
                    records.c.lifecycle_state == "inbox",
                    records.c.trashed_at.is_(None),
                )
                .values(
                    record_type="task",
                    lifecycle_state="task",
                    task_list=task_list,
                    task_active_since=changed_at,
                    updated_at=changed_at,
                )
            )
        return result.rowcount == 1

    def convert_processed_to_task(self, *, record_id: int, task_list: str, changed_at: str) -> bool:
        with transaction(self._engine) as connection:
            result = connection.execute(
                update(records)
                .where(
                    records.c.id == record_id,
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
                .values(
                    record_type="task",
                    lifecycle_state="task",
                    task_list=task_list,
                    task_active_since=changed_at,
                    updated_at=changed_at,
                )
            )
            if result.rowcount != 1:
                return False
            connection.execute(record_tags.delete().where(record_tags.c.record_id == record_id))
        return True

    def list_tags(self) -> list[TagOption]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(tags.c.id, tags.c.name).order_by(tags.c.sort_order, tags.c.id)
            ).all()
        return [TagOption(tag_id=row.id, name=row.name) for row in rows]

    def mark_inbox_processed_with_tags(
        self,
        *,
        record_id: int,
        tag_ids: tuple[int, ...],
        changed_at: str,
    ) -> bool:
        with transaction(self._engine) as connection:
            existing_tag_ids = {
                row.id for row in connection.execute(select(tags.c.id).where(tags.c.id.in_(tag_ids)))
            }
            selected_tag_ids = tuple(tag_id for tag_id in tag_ids if tag_id in existing_tag_ids)
            if not selected_tag_ids:
                return False
            result = connection.execute(
                update(records)
                .where(
                    records.c.id == record_id,
                    records.c.lifecycle_state == "inbox",
                    records.c.trashed_at.is_(None),
                )
                .values(lifecycle_state="processed", updated_at=changed_at)
            )
            if result.rowcount != 1:
                return False
            connection.execute(record_tags.delete().where(record_tags.c.record_id == record_id))
            connection.execute(
                insert(record_tags),
                [
                    {"record_id": record_id, "tag_id": tag_id, "assigned_at": changed_at}
                    for tag_id in selected_tag_ids
                ],
            )
        return True

    def move_inbox_to_trash(self, *, record_id: int, trashed_at: str) -> bool:
        with transaction(self._engine) as connection:
            existing = connection.execute(
                select(
                    records.c.lifecycle_state,
                    records.c.task_list,
                    records.c.completed_at,
                    records.c.hidden_at,
                ).where(
                    records.c.id == record_id,
                    records.c.lifecycle_state == "inbox",
                    records.c.trashed_at.is_(None),
                )
            ).one_or_none()
            if existing is None:
                return False
            connection.execute(
                update(records)
                .where(records.c.id == record_id)
                .values(
                    trashed_at=trashed_at,
                    pre_trash_lifecycle_state=existing.lifecycle_state,
                    pre_trash_task_list=existing.task_list,
                    pre_trash_completed_at=existing.completed_at,
                    pre_trash_hidden_at=existing.hidden_at,
                    updated_at=trashed_at,
                )
            )
            trash_rows = connection.execute(
                select(records.c.id)
                .where(records.c.trashed_at.is_not(None))
                .order_by(records.c.trashed_at.desc(), records.c.id.desc())
                .offset(30)
            ).all()
            if trash_rows:
                connection.execute(
                    records.delete().where(records.c.id.in_([row.id for row in trash_rows]))
                )
        return True

    def move_processed_to_trash(self, *, record_id: int, trashed_at: str) -> bool:
        with transaction(self._engine) as connection:
            existing = connection.execute(
                select(
                    records.c.lifecycle_state,
                    records.c.task_list,
                    records.c.completed_at,
                    records.c.hidden_at,
                ).where(
                    records.c.id == record_id,
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
            ).one_or_none()
            if existing is None:
                return False
            connection.execute(
                update(records)
                .where(records.c.id == record_id)
                .values(
                    trashed_at=trashed_at,
                    pre_trash_lifecycle_state=existing.lifecycle_state,
                    pre_trash_task_list=existing.task_list,
                    pre_trash_completed_at=existing.completed_at,
                    pre_trash_hidden_at=existing.hidden_at,
                    updated_at=trashed_at,
                )
            )
            trash_rows = connection.execute(
                select(records.c.id)
                .where(records.c.trashed_at.is_not(None))
                .order_by(records.c.trashed_at.desc(), records.c.id.desc())
                .offset(30)
            ).all()
            if trash_rows:
                connection.execute(
                    records.delete().where(records.c.id.in_([row.id for row in trash_rows]))
                )
        return True

    def list_processed(self) -> list[ProcessedRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    records.c.id,
                    records.c.display_text,
                    func.group_concat(tags.c.name, ", ").label("tag_names"),
                    records.c.updated_at,
                )
                .select_from(records)
                .outerjoin(record_tags, record_tags.c.record_id == records.c.id)
                .outerjoin(tags, tags.c.id == record_tags.c.tag_id)
                .where(
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
                .group_by(records.c.id)
                .order_by(records.c.updated_at.desc(), records.c.id.desc())
            ).all()
        return [
            ProcessedRecord(
                record_id=row.id,
                display_text=row.display_text,
                tags=tuple(tag for tag in (row.tag_names or "").split(", ") if tag),
            )
            for row in rows
        ]

    def get_processed_record(self, record_id: int) -> ProcessedRecord | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(
                    records.c.id,
                    records.c.display_text,
                    func.group_concat(tags.c.name, ", ").label("tag_names"),
                )
                .select_from(records)
                .outerjoin(record_tags, record_tags.c.record_id == records.c.id)
                .outerjoin(tags, tags.c.id == record_tags.c.tag_id)
                .where(
                    records.c.id == record_id,
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
                .group_by(records.c.id)
            ).one_or_none()
        if row is None:
            return None
        return ProcessedRecord(
            record_id=row.id,
            display_text=row.display_text,
            tags=tuple(tag for tag in (row.tag_names or "").split(", ") if tag),
        )

    def update_processed_tags(
        self,
        *,
        record_id: int,
        tag_ids: tuple[int, ...],
        changed_at: str,
    ) -> bool:
        with transaction(self._engine) as connection:
            existing = connection.execute(
                select(records.c.id).where(
                    records.c.id == record_id,
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
            ).one_or_none()
            if existing is None:
                return False
            existing_tag_ids = {
                row.id for row in connection.execute(select(tags.c.id).where(tags.c.id.in_(tag_ids)))
            }
            selected_tag_ids = tuple(tag_id for tag_id in tag_ids if tag_id in existing_tag_ids)
            if not selected_tag_ids:
                return False
            connection.execute(record_tags.delete().where(record_tags.c.record_id == record_id))
            connection.execute(
                insert(record_tags),
                [
                    {"record_id": record_id, "tag_id": tag_id, "assigned_at": changed_at}
                    for tag_id in selected_tag_ids
                ],
            )
            connection.execute(
                update(records)
                .where(records.c.id == record_id)
                .values(updated_at=changed_at)
            )
        return True

    def update_processed_text(self, *, record_id: int, display_text: str, changed_at: str) -> bool:
        with transaction(self._engine) as connection:
            result = connection.execute(
                update(records)
                .where(
                    records.c.id == record_id,
                    records.c.record_type == "thought",
                    records.c.lifecycle_state == "processed",
                    records.c.trashed_at.is_(None),
                )
                .values(display_text=display_text, updated_at=changed_at)
            )
        return result.rowcount == 1


class EveningReminderRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def prepare_reminder(
        self,
        *,
        job_name: str,
        period_key: str,
        started_at: str,
    ) -> EveningReminder | None:
        with transaction(self._engine) as connection:
            inbox_count = int(
                connection.scalar(
                    select(func.count())
                    .select_from(records)
                    .where(
                        records.c.lifecycle_state == "inbox",
                        records.c.trashed_at.is_(None),
                    )
                )
                or 0
            )
            current = connection.execute(
                select(scheduled_runs.c.status).where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.period_key == period_key,
                )
            ).one_or_none()
            if current is not None and current.status in {"running", "succeeded"}:
                return None

            previous = connection.execute(
                select(scheduled_runs.c.telegram_message_id)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.telegram_message_id.is_not(None),
                )
                .order_by(scheduled_runs.c.period_key.desc(), scheduled_runs.c.id.desc())
                .limit(1)
            ).one_or_none()
            previous_message_id = previous.telegram_message_id if previous is not None else None

            values = {
                "job_name": job_name,
                "period_key": period_key,
                "status": "running",
                "telegram_message_id": None,
                "details_json": json.dumps({"inbox_count": inbox_count}, sort_keys=True),
                "error_code": None,
                "started_at": started_at,
                "finished_at": None,
            }
            try:
                connection.execute(insert(scheduled_runs).values(**values))
            except IntegrityError:
                connection.execute(
                    update(scheduled_runs)
                    .where(
                        scheduled_runs.c.job_name == job_name,
                        scheduled_runs.c.period_key == period_key,
                        scheduled_runs.c.status != "succeeded",
                    )
                    .values(**{key: value for key, value in values.items() if key not in {"job_name", "period_key"}})
                )

        return EveningReminder(
            period_key=period_key,
            inbox_count=inbox_count,
            previous_message_id=previous_message_id,
        )

    def mark_sent(
        self,
        *,
        job_name: str,
        period_key: str,
        telegram_message_id: int,
        inbox_count: int,
        finished_at: str,
    ) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(scheduled_runs)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.period_key == period_key,
                )
                .values(
                    status="succeeded",
                    telegram_message_id=telegram_message_id,
                    details_json=json.dumps({"inbox_count": inbox_count}, sort_keys=True),
                    error_code=None,
                    finished_at=finished_at,
                )
            )
            connection.execute(
                update(scheduled_runs)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.period_key != period_key,
                )
                .values(telegram_message_id=None)
            )

    def mark_skipped_empty(
        self,
        *,
        job_name: str,
        period_key: str,
        finished_at: str,
    ) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(scheduled_runs)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.period_key == period_key,
                )
                .values(
                    status="succeeded",
                    telegram_message_id=None,
                    details_json=json.dumps({"inbox_count": 0}, sort_keys=True),
                    error_code=None,
                    finished_at=finished_at,
                )
            )

    def clear_message(self, *, job_name: str, telegram_message_id: int) -> None:
        with transaction(self._engine) as connection:
            connection.execute(
                update(scheduled_runs)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.telegram_message_id == telegram_message_id,
                )
                .values(telegram_message_id=None)
            )

    def get_active_message_id(self, *, job_name: str) -> int | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(scheduled_runs.c.telegram_message_id)
                .where(
                    scheduled_runs.c.job_name == job_name,
                    scheduled_runs.c.telegram_message_id.is_not(None),
                )
                .order_by(scheduled_runs.c.period_key.desc(), scheduled_runs.c.id.desc())
                .limit(1)
            ).one_or_none()
        if row is None:
            return None
        return row.telegram_message_id


class TaskRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_tasks(self, task_list: str) -> list[TaskRecord]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(
                    records.c.id,
                    records.c.display_text,
                    records.c.completed_at,
                )
                .where(
                    records.c.record_type == "task",
                    records.c.lifecycle_state == "task",
                    records.c.task_list == task_list,
                    records.c.trashed_at.is_(None),
                    records.c.hidden_at.is_(None),
                )
                .order_by(records.c.task_active_since, records.c.id)
            ).all()
        return [
            TaskRecord(
                record_id=row.id,
                display_text=row.display_text,
                completed=row.completed_at is not None,
            )
            for row in rows
        ]

    def toggle_completion(self, *, record_id: int, task_list: str, changed_at: str) -> bool:
        with transaction(self._engine) as connection:
            row = connection.execute(
                select(records.c.completed_at).where(
                    records.c.id == record_id,
                    records.c.record_type == "task",
                    records.c.lifecycle_state == "task",
                    records.c.task_list == task_list,
                    records.c.trashed_at.is_(None),
                    records.c.hidden_at.is_(None),
                )
            ).one_or_none()
            if row is None:
                return False
            connection.execute(
                update(records)
                .where(records.c.id == record_id)
                .values(
                    completed_at=None if row.completed_at is not None else changed_at,
                    updated_at=changed_at,
                )
            )
        return True
