import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol


class VoiceTranscriptionError(RuntimeError):
    """Raised when a voice message cannot be transcribed."""


class VoiceTranscriber(Protocol):
    def transcribe(self, audio_path: Path) -> str:
        """Return recognized text for a local audio file."""


class MissingVoiceTranscriber:
    def transcribe(self, _audio_path: Path) -> str:
        raise VoiceTranscriptionError("Deepgram API key is not configured")


class DeepgramTranscriber:
    _url = "https://api.deepgram.com/v1/listen?model=nova-2&language=ru&smart_format=true"

    def __init__(self, api_key: str, *, timeout_seconds: int = 60) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def transcribe(self, audio_path: Path) -> str:
        payload = audio_path.read_bytes()
        request = urllib.request.Request(
            self._url,
            data=payload,
            headers={
                "Authorization": f"Token {self._api_key}",
                "Content-Type": "audio/ogg",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                response_payload = response.read()
        except (OSError, urllib.error.URLError) as error:
            raise VoiceTranscriptionError("Deepgram request failed") from error

        try:
            data = json.loads(response_payload)
        except json.JSONDecodeError as error:
            raise VoiceTranscriptionError("Deepgram returned invalid JSON") from error

        transcript = _extract_transcript(data)
        if not transcript:
            raise VoiceTranscriptionError("Deepgram returned an empty transcript")
        return transcript


def build_voice_transcriber(api_key: str | None) -> VoiceTranscriber:
    if not api_key:
        return MissingVoiceTranscriber()
    return DeepgramTranscriber(api_key)


def _extract_transcript(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    results = data.get("results")
    if not isinstance(results, dict):
        return ""
    channels = results.get("channels")
    if not isinstance(channels, list) or not channels:
        return ""
    first_channel = channels[0]
    if not isinstance(first_channel, dict):
        return ""
    alternatives = first_channel.get("alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        return ""
    first_alternative = alternatives[0]
    if not isinstance(first_alternative, dict):
        return ""
    transcript = first_alternative.get("transcript")
    if not isinstance(transcript, str):
        return ""
    return transcript.strip()
