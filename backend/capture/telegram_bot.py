"""Telegram bot capture channel for JARVIS.

Receives photos via Telegram, downloads them, and feeds them into the pipeline.
Gracefully disabled when TELEGRAM_BOT_TOKEN is not configured.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from pipeline import CapturePipeline

try:
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters

    _TELEGRAM_AVAILABLE = True
except ImportError:
    _TELEGRAM_AVAILABLE = False


class TelegramCaptureBot:
    """Telegram bot that receives photos and runs them through the capture pipeline."""

    def __init__(self, token: str, pipeline: CapturePipeline) -> None:
        if not _TELEGRAM_AVAILABLE:
            raise RuntimeError("python-telegram-bot is not installed")
        self._token = token
        self._pipeline = pipeline
        self._app: Application | None = None  # type: ignore[type-arg]

    async def start(self) -> None:
        """Initialize and start polling in the background."""
        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, self._handle_photo)
        )

        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()  # type: ignore[union-attr]
        logger.info("Telegram capture bot started polling")

    async def stop(self) -> None:
        """Gracefully shut down the bot."""
        if self._app is None:
            return
        await self._app.updater.stop()  # type: ignore[union-attr]
        await self._app.stop()
        await self._app.shutdown()
        logger.info("Telegram capture bot stopped")

    @staticmethod
    async def _handle_start(update: Update, _context: object) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "JARVIS capture bot ready. Send a photo to analyze."
            )

    async def _handle_photo(self, update: Update, _context: object) -> None:
        message = update.effective_message
        if message is None:
            return

        # Prefer highest resolution photo, fall back to document
        if message.photo:
            file_obj = await message.photo[-1].get_file()
        elif message.document:
            file_obj = await message.document.get_file()
        else:
            await message.reply_text("No image found in message.")
            return

        data = await file_obj.download_as_bytearray()
        logger.info("Telegram photo received, {} bytes", len(data))

        from uuid import uuid4

        capture_id = f"cap_{uuid4().hex[:12]}"
        try:
            result = await self._pipeline.process(
                capture_id=capture_id,
                data=bytes(data),
                content_type="image/jpeg",
                source="telegram",
            )
            await message.reply_text(
                f"Processed {capture_id}: {result.faces_detected} face(s) detected, "
                f"{len(result.persons_created)} person(s) created."
            )
        except Exception as exc:
            logger.error("Telegram pipeline error: {}", exc)
            await message.reply_text(f"Processing failed: {exc}")


def create_telegram_bot(token: str | None, pipeline: CapturePipeline) -> TelegramCaptureBot | None:
    """Factory that returns None when token is missing or library unavailable."""
    if not token:
        logger.info("TELEGRAM_BOT_TOKEN not set, Telegram bot disabled")
        return None
    if not _TELEGRAM_AVAILABLE:
        logger.warning("python-telegram-bot not installed, Telegram bot disabled")
        return None
    return TelegramCaptureBot(token=token, pipeline=pipeline)
