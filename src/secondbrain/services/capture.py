import unicodedata
from datetime import datetime
from ipaddress import ip_address
from urllib.parse import urlparse

from secondbrain.models.records import CapturedRecord, PendingConfirmation
from secondbrain.storage.database import utc_now_text
from secondbrain.storage.repositories import CaptureRepository

PREFIXES = (
    ("на этой неделе", "week"),
    ("сегодня", "today"),
    ("завтра", "tomorrow"),
)


class CaptureService:
    def __init__(self, repository: CaptureRepository) -> None:
        self._repository = repository

    def capture_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        raw_text: str,
        telegram_sent_at: datetime,
    ) -> CapturedRecord:
        display_text, task_list = parse_text(raw_text)
        received_at = utc_now_text()
        link_metadata_url = detect_standalone_link(raw_text) if task_list is None else None
        return self._repository.create(
            chat_id=chat_id,
            message_id=message_id,
            raw_text=raw_text,
            display_text=display_text,
            record_type="task" if task_list else "thought",
            lifecycle_state="task" if task_list else "inbox",
            task_list=task_list,
            link_metadata_url=link_metadata_url,
            telegram_sent_at=telegram_sent_at.isoformat(timespec="seconds"),
            received_at=received_at,
        )

    def mark_confirmed(self, *, chat_id: int, message_id: int) -> None:
        self._repository.mark_confirmed(
            chat_id=chat_id,
            message_id=message_id,
            confirmed_at=utc_now_text(),
        )

    def get_next_unconfirmed(self, *, chat_id: int) -> PendingConfirmation | None:
        return self._repository.get_next_unconfirmed(chat_id=chat_id)

    def mark_confirmation_sent(self, *, source_message_id: int) -> None:
        self._repository.mark_confirmed_by_source_id(
            source_message_id=source_message_id,
            confirmed_at=utc_now_text(),
        )


def parse_text(raw_text: str) -> tuple[str, str | None]:
    folded = raw_text.casefold()
    for prefix, task_list in PREFIXES:
        if not folded.startswith(prefix) or len(raw_text) == len(prefix):
            continue
        boundary = raw_text[len(prefix)]
        if not (boundary.isspace() or unicodedata.category(boundary).startswith("P")):
            continue
        remainder = raw_text[len(prefix) :]
        separator_length = 0
        while separator_length < len(remainder) and _is_separator(remainder[separator_length]):
            separator_length += 1
        display_text = remainder[separator_length:]
        if display_text:
            return _uppercase_first(display_text), task_list
    return raw_text, None


def _is_separator(character: str) -> bool:
    return character.isspace() or unicodedata.category(character).startswith("P")


def _uppercase_first(text: str) -> str:
    return text[0].upper() + text[1:]


def detect_standalone_link(raw_text: str) -> str | None:
    text = raw_text.strip()
    if not text or any(character.isspace() for character in text):
        return None

    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc or parsed.username or parsed.password:
        return None

    hostname = parsed.hostname
    if hostname is None or hostname.casefold() == "localhost":
        return None

    try:
        address = ip_address(hostname)
    except ValueError:
        return text
    if not address.is_global:
        return None
    return text
