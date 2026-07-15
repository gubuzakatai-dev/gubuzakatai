from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

records = Table(
    "records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("display_text", Text, nullable=False),
    Column("record_type", Text, nullable=False),
    Column("lifecycle_state", Text, nullable=False),
    Column("task_list", Text),
    Column("completed_at", Text),
    Column("task_active_since", Text),
    Column("stale_prompted_at", Text),
    Column("stale_prompt_message_id", Integer),
    Column("hidden_at", Text),
    Column("trashed_at", Text),
    Column("pre_trash_lifecycle_state", Text),
    Column("pre_trash_task_list", Text),
    Column("pre_trash_completed_at", Text),
    Column("pre_trash_hidden_at", Text),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("length(trim(display_text)) > 0", name="ck_records_display_text"),
    CheckConstraint("record_type IN ('thought', 'task')", name="ck_records_type"),
    CheckConstraint(
        "lifecycle_state IN ('inbox', 'processed', 'task')", name="ck_records_lifecycle"
    ),
    CheckConstraint(
        "task_list IS NULL OR task_list IN ('today', 'tomorrow', 'week')",
        name="ck_records_task_list",
    ),
    CheckConstraint(
        "(record_type = 'task' AND lifecycle_state = 'task' AND task_list IS NOT NULL) OR "
        "(record_type = 'thought' AND lifecycle_state IN ('inbox', 'processed') "
        "AND task_list IS NULL AND completed_at IS NULL AND task_active_since IS NULL "
        "AND stale_prompted_at IS NULL AND stale_prompt_message_id IS NULL AND hidden_at IS NULL)",
        name="ck_records_type_state",
    ),
)
Index("ix_records_state_list_created", records.c.lifecycle_state, records.c.task_list, records.c.created_at)
Index("ix_records_type_active", records.c.record_type, records.c.task_active_since)
Index("ix_records_trashed", records.c.trashed_at)

source_messages = Table(
    "source_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("record_id", ForeignKey("records.id", ondelete="CASCADE"), nullable=False, unique=True),
    Column("telegram_chat_id", Integer, nullable=False),
    Column("telegram_message_id", Integer, nullable=False),
    Column("raw_text", Text, nullable=False),
    Column("telegram_sent_at", Text, nullable=False),
    Column("received_at", Text, nullable=False),
    Column("confirmation_sent_at", Text),
    Column("created_at", Text, nullable=False),
    UniqueConstraint("telegram_chat_id", "telegram_message_id", name="uq_source_telegram"),
    CheckConstraint("length(trim(raw_text)) > 0", name="ck_source_raw_text"),
)
Index(
    "ix_source_confirmation_queue",
    source_messages.c.telegram_chat_id,
    source_messages.c.confirmation_sent_at,
    source_messages.c.telegram_sent_at,
    source_messages.c.telegram_message_id,
)

tags = Table(
    "tags",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", Text, nullable=False),
    Column("normalized_name", Text, nullable=False, unique=True),
    Column("is_system", Boolean, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    CheckConstraint("length(trim(name)) BETWEEN 1 AND 15", name="ck_tags_name_length"),
    CheckConstraint("length(trim(normalized_name)) > 0", name="ck_tags_normalized_name"),
    CheckConstraint("is_system IN (0, 1)", name="ck_tags_is_system"),
)

record_tags = Table(
    "record_tags",
    metadata,
    Column("record_id", ForeignKey("records.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", Text, nullable=False),
)
Index("ix_record_tags_tag_record", record_tags.c.tag_id, record_tags.c.record_id)

processing_results = Table(
    "processing_results",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("record_id", ForeignKey("records.id", ondelete="CASCADE"), nullable=False),
    Column("source_message_id", ForeignKey("source_messages.id", ondelete="SET NULL")),
    Column("operation", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("input_text", Text),
    Column("output_text", Text),
    Column("output_json", Text),
    Column("error_code", Text),
    Column("error_message", Text),
    Column("attempt_no", Integer, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("started_at", Text),
    Column("finished_at", Text),
    CheckConstraint("operation = 'link_metadata'", name="ck_results_operation"),
    CheckConstraint("status IN ('pending', 'running', 'succeeded', 'failed')", name="ck_results_status"),
    CheckConstraint("attempt_no >= 1", name="ck_results_attempt"),
    CheckConstraint("output_json IS NULL OR json_valid(output_json)", name="ck_results_json"),
    CheckConstraint(
        "status != 'succeeded' OR output_text IS NOT NULL OR output_json IS NOT NULL",
        name="ck_results_success_output",
    ),
    CheckConstraint("status != 'failed' OR error_code IS NOT NULL", name="ck_results_failed_error"),
)
Index(
    "ix_results_record_operation_created",
    processing_results.c.record_id,
    processing_results.c.operation,
    processing_results.c.created_at,
)

scheduled_runs = Table(
    "scheduled_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("job_name", Text, nullable=False),
    Column("period_key", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("telegram_message_id", Integer),
    Column("details_json", Text),
    Column("error_code", Text),
    Column("started_at", Text, nullable=False),
    Column("finished_at", Text),
    UniqueConstraint("job_name", "period_key", name="uq_scheduled_period"),
    CheckConstraint("status IN ('running', 'succeeded', 'failed')", name="ck_scheduled_status"),
    CheckConstraint("details_json IS NULL OR json_valid(details_json)", name="ck_scheduled_json"),
)

bot_sessions = Table(
    "bot_sessions",
    metadata,
    Column("telegram_user_id", Integer, primary_key=True),
    Column("state", Text, nullable=False),
    Column("record_id", ForeignKey("records.id", ondelete="SET NULL")),
    Column("context_json", Text, nullable=False),
    Column("created_at", Text, nullable=False),
    Column("updated_at", Text, nullable=False),
    Column("expires_at", Text, nullable=False),
    CheckConstraint("length(trim(state)) > 0", name="ck_sessions_state"),
    CheckConstraint("json_valid(context_json)", name="ck_sessions_json"),
)
Index("ix_sessions_expires", bot_sessions.c.expires_at)
