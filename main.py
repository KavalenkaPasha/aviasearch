import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers.start import router as start_router
from handlers.search import router as search_router

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(search_router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
logging.basicConfig(level=logging.DEBUG)