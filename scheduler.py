# 📄 файл: scheduler.py
import asyncio
import logging
from datetime import datetime

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import Config
from database import get_db, mark_session_warned, mark_session_aborted

logger = logging.getLogger(__name__)


async def start_scheduler(bot: Bot, config: Config):
    """Фоновая задача: проверяет сессии каждые 60 сек."""
    while True:
        try:
            await asyncio.sleep(config.SCHEDULER_INTERVAL)
            await _check_sessions(bot, config)
            await _check_meal_timers(bot, config)
            await _check_monthly_report(bot, config)
        except asyncio.CancelledError:
            logger.info("Планировщик остановлен.")
            break
        except Exception as e:
            logger.exception(f"Ошибка в планировщике: {e}")


def resume_keyboard() -> InlineKeyboardMarkup:
    """БАГ 2 — кнопка 'Продолжить' в напоминании."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="resume_survey")]
    ])


# ---------------------------------------------------------------------------
# Проверка таймаутов сессий
# ---------------------------------------------------------------------------

async def _check_sessions(bot: Bot, config: Config):
    async with get_db() as db:
        # active → warned (20 мин тишины)
        cursor = await db.execute(
            """
            SELECT id, user_id
            FROM sessions
            WHERE status = 'active'
              AND (julianday('now') - julianday(last_interaction)) * 86400 > ?
            """,
            (config.WARN_TIMEOUT,)
        )
        to_warn = await cursor.fetchall()

        for row in to_warn:
            try:
                await mark_session_warned(db, row["id"])
                await bot.send_message(
                    row["user_id"],
                    "⏳ Ты ещё здесь? Можем продолжить опрос.\n"
                    "Через 20 минут сессия закроется, но данные сохранятся.",
                    reply_markup=resume_keyboard()   # ← БАГ 2 починен
                )
                logger.info(f"Предупреждение отправлено: session_id={row['id']}")
            except Exception as e:
                logger.warning(f"Не удалось отправить предупреждение {row['id']}: {e}")

        # warned → aborted (ещё 20 мин тишины)
        cursor = await db.execute(
            """
            SELECT id, user_id, answers_json
            FROM sessions
            WHERE status = 'warned'
              AND (julianday('now') - julianday(last_interaction)) * 86400 > ?
            """,
            (config.ABORT_TIMEOUT,)
        )
        to_abort = await cursor.fetchall()

        for row in to_abort:
            try:
                await mark_session_aborted(db, row["id"])
                if row["answers_json"] and row["answers_json"] != "{}":
                    await db.execute(
                        "UPDATE meals SET is_complete = 0 WHERE session_id = ? AND is_complete = 0",
                        (row["id"],)
                    )
                    await db.commit()
                await bot.send_message(
                    row["user_id"],
                    "📁 Сессия завершена по таймауту. "
                    "Частичные данные сохранены.\n\n"
                    "Когда будешь готова — нажми «мне грустно» чтобы начать заново."
                )
                logger.info(f"Сессия прервана: session_id={row['id']}")
            except Exception as e:
                logger.warning(f"Не удалось завершить сессию {row['id']}: {e}")


# ---------------------------------------------------------------------------
# Таймер 30 минут → запуск опросника 2
# ---------------------------------------------------------------------------

async def _check_meal_timers(bot: Bot, config: Config):
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT s.id AS session_id, s.user_id, m.id AS meal_id
            FROM sessions s
            JOIN meals m ON m.session_id = s.id
            WHERE s.status IN ('active', 'warned')
              AND s.current_step = 'waiting_part2'
              AND m.is_complete = 0
              AND m.timestamp_part2 IS NULL
              AND (julianday('now') - julianday(m.timestamp_part1)) * 86400 > ?
            """,
            (config.MEAL_TIMER,)
        )
        rows = await cursor.fetchall()

        for row in rows:
            try:
                await db.execute(
                    """
                    UPDATE sessions
                    SET current_step = 'q2_step_0',
                        last_interaction = datetime('now')
                    WHERE id = ?
                    """,
                    (row["session_id"],)
                )
                await db.commit()

                from keyboards.questionnaire2 import start_q2_keyboard
                await bot.send_message(
                    row["user_id"],
                    "🍽 Прошло 30 минут. Как ты сейчас?\n"
                    "Давай заполним второй опрос — это займёт пару минут.",
                    reply_markup=start_q2_keyboard()
                )
                logger.info(f"Запущен опросник 2 по таймеру: session_id={row['session_id']}")
            except Exception as e:
                logger.warning(f"Ошибка запуска опросника 2 для session {row['session_id']}: {e}")


# ---------------------------------------------------------------------------
# Ежемесячная сводка (1-го числа в 10:00)
# ---------------------------------------------------------------------------

async def _check_monthly_report(bot: Bot, config: Config):
    now = datetime.now()
    if now.day != config.MONTHLY_REPORT_DAY:
        return
    if now.hour != 10 or now.minute > 1:
        return

    async with get_db() as db:
        marker = int(f"9{now.year}{now.month:02d}")
        cursor = await db.execute(
            "SELECT COUNT(*) FROM schema_version WHERE version = ?",
            (marker,)
        )
        row = await cursor.fetchone()
        if row[0] > 0:
            return

        try:
            report = await _build_monthly_report(db)
            cursor = await db.execute("SELECT id FROM users")
            users = await cursor.fetchall()
            for user in users:
                await bot.send_message(user["id"], report)
            await db.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (marker,)
            )
            await db.commit()
            logger.info("Ежемесячная сводка отправлена.")
        except Exception as e:
            logger.exception(f"Ошибка формирования сводки: {e}")


async def _build_monthly_report(db) -> str:
    now = datetime.now()
    month_start = f"{now.year}-{now.month:02d}-01"

    cursor = await db.execute(
        "SELECT COUNT(*) AS total FROM sessions WHERE created_at >= ?",
        (month_start,)
    )
    row = await cursor.fetchone()
    total = row["total"] if row else 0

    cursor = await db.execute(
        "SELECT COUNT(*) AS done FROM sessions WHERE created_at >= ? AND status = 'complete'",
        (month_start,)
    )
    row = await cursor.fetchone()
    complete = row["done"] if row else 0

    cursor = await db.execute(
        """
        SELECT
            CASE
                WHEN CAST(strftime('%H', created_at) AS INTEGER) BETWEEN 6 AND 11
                    THEN 'утро (6-11)'
                WHEN CAST(strftime('%H', created_at) AS INTEGER) BETWEEN 12 AND 17
                    THEN 'день (12-17)'
                WHEN CAST(strftime('%H', created_at) AS INTEGER) BETWEEN 18 AND 22
                    THEN 'вечер (18-22)'
                ELSE 'ночь (23-5)'
            END AS period,
            COUNT(*) AS cnt
        FROM sessions
        WHERE created_at >= ?
        GROUP BY period
        ORDER BY cnt DESC
        """,
        (month_start,)
    )
    by_time = await cursor.fetchall()

    cursor = await db.execute(
        """
        SELECT
            CASE strftime('%w', created_at)
                WHEN '0' THEN 'Воскресенье'
                WHEN '1' THEN 'Понедельник'
                WHEN '2' THEN 'Вторник'
                WHEN '3' THEN 'Среда'
                WHEN '4' THEN 'Четверг'
                WHEN '5' THEN 'Пятница'
                WHEN '6' THEN 'Суббота'
            END AS weekday,
            COUNT(*) AS cnt
        FROM sessions
        WHERE created_at >= ?
        GROUP BY weekday
        ORDER BY cnt DESC
        """,
        (month_start,)
    )
    by_weekday = await cursor.fetchall()

    lines = [
        f"📊 Сводка за {now.strftime('%B %Y')}",
        "",
        f"Всего запусков: {total}",
        f"Завершено полностью: {complete}",
        "",
        "🕐 По времени суток:",
    ]
    for r in by_time:
        lines.append(f"  {r['period']}: {r['cnt']}")
    lines.append("")
    lines.append("📅 По дням недели:")
    for r in by_weekday:
        lines.append(f"  {r['weekday']}: {r['cnt']}")

    return "\n".join(lines)