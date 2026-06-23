import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import Job


router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("start"))
async def start(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    await message.answer(
        "Transcriber bot is ready.\n"
        f"Your Telegram user id: {user_id}\n"
        "Use this id in iOS Shortcut as telegram_user_id.\n"
        "Check a job with: /status job_id"
    )


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else message.chat.id
    await message.answer(str(user_id))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await start(message)


@router.message(Command("status"))
async def status(message: Message, command: CommandObject) -> None:
    job_id = (command.args or "").strip()
    if not job_id:
        await message.answer("Send job_id: /status job_...")
        return

    with SessionLocal() as db:
        job = db.get(Job, job_id)

    if not job:
        await message.answer("Job not found.")
        return

    text = [
        f"Job: {job.id}",
        f"Status: {job.status}",
    ]
    if job.error:
        text.append(f"Error: {job.error}")
    await message.answer("\n".join(text))


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the bot")

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
