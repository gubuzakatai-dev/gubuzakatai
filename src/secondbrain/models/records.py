from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapturedRecord:
    record_id: int
    display_text: str
    destination: str
    confirmation_required: bool


@dataclass(frozen=True, slots=True)
class PendingConfirmation:
    source_message_id: int
    chat_id: int
    record_id: int
    display_text: str
    destination: str
