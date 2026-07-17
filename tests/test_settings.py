import logging

import pytest

from secondbrain.app import configure_logging
from secondbrain.config.settings import load_settings


def test_load_settings_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        load_settings()


def test_load_settings_parses_allowed_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.setenv("DEEPGRAM_API_KEY", "deepgram-key")

    settings = load_settings()

    assert settings.telegram_bot_token == "test-token"
    assert settings.telegram_allowed_user_id == 123
    assert settings.deepgram_api_key == "deepgram-key"


def test_load_settings_allows_missing_deepgram_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "123")
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    settings = load_settings()

    assert settings.deepgram_api_key is None


def test_httpx_info_logging_is_disabled() -> None:
    configure_logging()

    assert logging.getLogger("httpx").level == logging.WARNING
