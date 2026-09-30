"""Server-side voice command processing via Gemini audio transcription.

# RESEARCH: Gemini 2.0 Flash supports inline audio (webm/opus), fast + free tier
# DECISION: Use Gemini for transcription — already configured, no extra API key
# ALT: OpenAI Whisper (requires separate API key), local whisper.cpp (latency)
"""

from __future__ import annotations

import base64
import re

from loguru import logger

COMMAND_PATTERNS: list[tuple[str, str]] = [
    (r"\btarget\b", "TARGET_CONFIRMED"),
    (r"\block\s*on\b", "LOCK_ON"),
    (r"\bscan\b", "SCAN_INITIATED"),
    (r"\bbrief\s*(me)?\b", "BRIEF_ME"),
    (r"\bresearch\s+(.+)", "RESEARCH"),
]


class AudioCommandProcessor:
    """Processes audio chunks: transcribes via Gemini, matches voice commands."""

    def __init__(self, gemini_api_key: str, gemini_models: str | None = None):
        from gemini_pool import GeminiRotator

        self._rotator = GeminiRotator(gemini_api_key, gemini_models)

    async def transcribe_chunk(self, audio_bytes: bytes) -> str:
        """Transcribe audio bytes via Gemini Flash with inline audio."""
        import asyncio

        b64_audio = base64.b64encode(audio_bytes).decode()
        try:
            result = await asyncio.to_thread(
                self._rotator.generate_content,
                contents=[
                    {
                        "parts": [
                            {
                                "inline_data": {
                                    "mime_type": "audio/webm",
                                    "data": b64_audio,
                                }
                            },
                            {
                                "text": (
                                    "Transcribe this short audio clip exactly. "
                                    "Return only the spoken words, nothing else. "
                                    "If silent or unintelligible, return empty string."
                                )
                            },
                        ]
                    }
                ],
            )
            text = result.text.strip() if result.text else ""
            # Gemini sometimes wraps in quotes — strip them
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]
            return text
        except Exception as exc:
            logger.warning("audio_handler: transcription failed: {}", exc)
            return ""

    def match_command(self, transcript: str) -> tuple[str, str | None]:
        """Match transcript against command patterns.

        Returns (command_type, argument) — ("NONE", None) if no match.
        """
        text = transcript.lower().strip()
        if not text:
            return ("NONE", None)
        for pattern, cmd_type in COMMAND_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                arg = m.group(1) if m.lastindex else None
                return (cmd_type, arg)
        return ("NONE", None)
