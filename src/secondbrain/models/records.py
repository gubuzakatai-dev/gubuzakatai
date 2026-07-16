from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CapturedRecord:
    record_id: int
    display_text: str
    destination: str
    confirmation_required: bool

