from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile

from app.config import Settings
from app.models import Job


async def send_message(settings: Settings, chat_id: str | None, text: str) -> None:
    if not settings.telegram_bot_token or not chat_id:
        return

    bot = Bot(token=settings.telegram_bot_token)
    try:
        await bot.send_message(chat_id, text)
    finally:
        await bot.session.close()


async def send_job_files(settings: Settings, job: Job) -> None:
    if not settings.telegram_bot_token or not job.user_id:
        return

    bot = Bot(token=settings.telegram_bot_token)
    try:
        base_name = telegram_result_basename(job)
        files = [
            (job.raw_json_path, f"{base_name}.json"),
            (job.result_txt_path, f"{base_name}.txt"),
        ]
        for path_text, filename in files:
            if path_text and Path(path_text).exists():
                await bot.send_document(job.user_id, FSInputFile(path_text, filename=filename))
    finally:
        await bot.session.close()


def telegram_result_basename(job: Job) -> str:
    created_at = job.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d-%H-%M-%S")
