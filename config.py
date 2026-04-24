# 📄 файл: config.py
import os
from dataclasses import dataclass

@dataclass
class Config:
    BOT_TOKEN: str
    DB_PATH: str = "data/bot.db"
    LOG_PATH: str = "data/bot.log"

    # Таймауты сессии (в секундах)
    WARN_TIMEOUT: int = 20 * 60       # 20 минут → предупреждение
    ABORT_TIMEOUT: int = 40 * 60      # 40 минут → сессия aborted
    MEAL_TIMER: int = 30 * 60         # 30 минут → запуск опросника 2
    SCHEDULER_INTERVAL: int = 60      # Интервал фоновой проверки

    # Ежемесячная сводка: день месяца
    MONTHLY_REPORT_DAY: int = 1


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не задан в переменных окружения (.env или системных)")
    return Config(BOT_TOKEN=token)