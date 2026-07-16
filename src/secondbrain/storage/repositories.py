from sqlalchemy import Engine, insert, select, update
from sqlalchemy.exc import IntegrityError

from secondbrain.models.records import CapturedRecord
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
