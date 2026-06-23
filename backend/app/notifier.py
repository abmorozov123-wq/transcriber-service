from pathlib import Path

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
        await bot.send_message(job.user_id, f"Done.\nJob: {job.id}")
        for path_text in (job.result_md_path, job.result_txt_path):
            if path_text and Path(path_text).exists():
                await bot.send_document(job.user_id, FSInputFile(path_text))
    finally:
        await bot.session.close()
