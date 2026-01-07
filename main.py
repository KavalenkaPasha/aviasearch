# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from handlers.start import router as start_router
from handlers.search import router as search_router

# Настройка логирования раньше, чтобы видеть логи с самого старта
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def run_bot():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(search_router)

    # Если polling падает из-за сетевой ошибки — делаем повтор с экспоненциальным бэкоффом.
    backoff = 1
    try:
        while True:
            try:
                logger.info("Starting polling...")
                await dp.start_polling(bot)
                logger.info("Polling finished without exception.")
                break
            except asyncio.CancelledError:
                # Позже можно специально остановить ожидание
                logger.info("Polling cancelled.")
                raise
            except Exception as exc:
                logger.exception("Polling crashed with exception. Retrying in %s seconds...", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
    finally:
        # Пытаемся корректно закрыть соединения бота
        try:
            await bot.session.close()
        except Exception:
            try:
                await bot.close()
            except Exception:
                logger.debug("Bot close failed", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt).")
