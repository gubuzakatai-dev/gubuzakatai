import json
from dataclasses import dataclass

from sqlalchemy import Engine, func, insert, select, update
from sqlalchemy.exc import IntegrityError

from secondbrain.models.records import CapturedRecord, InboxRecord, PendingConfirmation, ReviewRecord
from secondbrain.storage.database import transaction
from secondbrain.storage.schema import processing_results, records, source_messages


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
