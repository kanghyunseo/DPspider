"""OpenAI Whisper transcription wrapper for voice messages."""
from pathlib import Path

from openai import OpenAI

from . import config


def transcribe(audio_path: str | Path, language: str | None = None) -> str:
    """Transcribe an audio file via OpenAI Whisper API.

    Raises RuntimeError if OPENAI_API_KEY is not configured.
    """
    if not config.OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY 가 설정되지 않아 음성 메시지를 처리할 수 없습니다. "
            ".env 또는 Railway Variables 에 키를 추가하세요."
        )

    client = OpenAI(api_key=config.OPENAI_API_KEY)
    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language or config.WHISPER_LANGUAGE,
        )
    return transcript.text.strip()
