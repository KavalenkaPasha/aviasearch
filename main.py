# main.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, ADMIN_ID
from handlers.start import router as start_router
from handlers.search import router as search_router
from handlers.subscription import router as sub_router
from services.scheduler import check_subscriptions_task
from database import init_db, get_subscriptions_count
from ui.keyboards import main_menu

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    """Действия при запуске бота"""
    try:
        if ADMIN_ID:
            count = get_subscriptions_count()
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=(
                    f"🚀 <b>Бот успешно запущен!</b>\n"
                    f"📊 Активных подписок: {count}\n"
                    f"Навигация активирована 👇"
                ),
                reply_markup=main_menu(),
                parse_mode="HTML"
            )
            logger.info(f"Startup message sent to admin {ADMIN_ID}")
        else:
            logger.warning("ADMIN_ID not set in .env, skipping startup message")
    except Exception as e:
        logger.error(f"Failed to send startup message: {e}")

async def run_bot():
    init_db()
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start_router)
    dp.include_router(search_router)
    dp.include_router(sub_router)

    # Запускаем задачу планировщика
    asyncio.create_task(check_subscriptions_task(bot))

    # Уведомление о старте
    await on_startup(bot)

    logger.info("Starting polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")