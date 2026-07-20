from pathlib import Path

import pytest

from secondbrain.services.voice import (
    DeepgramTranscriber,
    MissingVoiceTranscriber,
    VoiceTranscriptionError,
    _extract_transcript,
    build_voice_transcriber,
)


def test_extract_transcript_from_deepgram_response() -> None:
    data = {
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "transcript": " Сегодня купить молоко ",
                        }
                    ]
                }
            ]
        }
    }

    assert _extract_transcript(data) == "Сегодня купить молоко"


def test_extract_transcript_returns_empty_for_unexpected_response() -> None:
    assert _extract_transcript({"results": {"channels": []}}) == ""


def test_build_voice_transcriber_requires_key() -> None:
    transcriber = build_voice_transcriber(None)

    assert isinstance(transcriber, MissingVoiceTranscriber)
    with pytest.raises(VoiceTranscriptionError):
        transcriber.transcribe(Path("voice.ogg"))


def test_build_voice_transcriber_uses_deepgram_when_key_exists() -> None:
    transcriber = build_voice_transcriber("key")

    assert isinstance(transcriber, DeepgramTranscriber)
