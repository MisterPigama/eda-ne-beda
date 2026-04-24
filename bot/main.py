# 📄 файл: bot/main.py
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from database import init_db
from scheduler import start_scheduler

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------

os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("data/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Регистрация роутеров
# ---------------------------------------------------------------------------

def register_routers(dp: Dispatcher):
    from handlers.start import router as start_router
    from handlers.questionnaire1 import router as q1_router
    from handlers.questionnaire2 import router as q2_router
    from handlers.export import router as export_router
    from handlers.admin import router as admin_router

    dp.include_router(start_router)
    dp.include_router(q1_router)
    dp.include_router(q2_router)
    dp.include_router(export_router)
    dp.include_router(admin_router)


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

async def main():
    config = load_config()

    await init_db()
    logger.info("База данных готова.")

    storage = MemoryStorage()
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=storage)

    register_routers(dp)
    logger.info("Роутеры зарегистрированы.")

    scheduler_task = asyncio.create_task(start_scheduler(bot, config))
    logger.info("Планировщик запущен.")

    try:
        logger.info("Бот запущен. Polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler_task.cancel()
        try:
            await scheduler_task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    asyncio.run(main())