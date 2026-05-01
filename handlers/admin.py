# 📄 файл: handlers/admin.py
import logging
import json
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from database import get_db

logger = logging.getLogger(__name__)
router = Router()


# ---------------------------------------------------------------------------
# /reset_quarter — бэкап и очистка данных за прошлый квартал
# ---------------------------------------------------------------------------

@router.message(Command("reset_quarter"))
async def cmd_reset_quarter(message: Message):
    user_id = message.from_user.id
    try:
        import shutil
        import os
        from datetime import datetime

        now = datetime.now()
        quarter = (now.month - 1) // 3 + 1
        backup_name = f"data/backup_Q{quarter}_{now.year}.db"

        # Бэкап текущей БД
        shutil.copy2("data/bot.db", backup_name)
        logger.info(f"Бэкап создан: {backup_name}")

        await message.answer(
            f"✅ Бэкап создан: `{backup_name}`\n\n"
            f"Данные сохранены. Основная БД не тронута.\n"
            f"Если хочешь — могу также выгрузить архив через /export.",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.exception(f"Ошибка reset_quarter: {e}")
        await message.answer("Не удалось создать бэкап. Проверь логи.")


# ---------------------------------------------------------------------------
# /stats — быстрая сводка прямо сейчас (без ожидания 1-го числа)
# ---------------------------------------------------------------------------

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    user_id = message.from_user.id
    try:
        async with get_db() as db:
            # Общая статистика
            cursor = await db.execute(
                "SELECT COUNT(*) AS total FROM sessions WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            total = row["total"] if row else 0

            cursor = await db.execute(
                """
                SELECT status, COUNT(*) AS cnt
                FROM sessions WHERE user_id = ?
                GROUP BY status
                """,
                (user_id,)
            )
            by_status = await cursor.fetchall()

            cursor = await db.execute(
                """
                SELECT COUNT(*) AS done FROM meals
                WHERE user_id = ? AND is_complete = 1
                """,
                (user_id,)
            )
            row = await cursor.fetchone()
            complete_meals = row["done"] if row else 0

            # Средние значения по шкалам
            cursor = await db.execute(
                """
                SELECT part1_data_json, part2_data_json
                FROM meals WHERE user_id = ? AND is_complete = 1
                """,
                (user_id,)
            )
            meal_rows = await cursor.fetchall()

            hunger_vals = []
            satisfaction_vals = []
            sleepiness_vals = []

            for r in meal_rows:
                try:
                    p1 = json.loads(r["part1_data_json"] or "{}")
                    p2 = json.loads(r["part2_data_json"] or "{}")
                    if "hunger_score" in p1:
                        hunger_vals.append(p1["hunger_score"])
                    if "sleepiness" in p1:
                        sleepiness_vals.append(p1["sleepiness"])
                    if "satisfaction" in p2:
                        satisfaction_vals.append(p2["satisfaction"])
                except Exception:
                    pass

            def avg(lst):
                return f"{sum(lst)/len(lst):.1f}" if lst else "—"

            # По времени суток
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
                WHERE user_id = ?
                GROUP BY period
                ORDER BY cnt DESC
                """,
                (user_id,)
            )
            by_time = await cursor.fetchall()

            # Сборка ответа
            lines = ["📊 *Статистика*", ""]
            lines.append(f"Всего сессий: {total}")

            status_map = {
                "complete": "завершено",
                "aborted": "прервано",
                "active": "активных",
                "warned": "с предупреждением",
                "incomplete": "неполных",
            }
            for r in by_status:
                label = status_map.get(r["status"], r["status"])
                lines.append(f"  {label}: {r['cnt']}")

            lines.append(f"Полных записей еды: {complete_meals}")
            lines.append("")
            lines.append("📈 Средние значения:")
            lines.append(f"  Голод до еды: {avg(hunger_vals)}")
            lines.append(f"  Удовлетворение: {avg(satisfaction_vals)}")
            lines.append(f"  Сонливость: {avg(sleepiness_vals)}")

            if by_time:
                lines.append("")
                lines.append("🕐 По времени суток:")
                for r in by_time:
                    lines.append(f"  {r['period']}: {r['cnt']}")

            await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as e:
        logger.exception(f"Ошибка /stats: {e}")
        await message.answer("Не удалось получить статистику. Проверь логи.")
        # ---------------------------------------------------------------------------
# /report_test — тестовый отчёт за произвольный период
# Формат: /report_test YYYY-MM-DD YYYY-MM-DD
# Пример: /report_test 2026-04-01 2026-04-30
# ---------------------------------------------------------------------------

@router.message(Command("report_test"))
async def cmd_report_test(message: Message):
    user_id = message.from_user.id
    args = message.text.split()[1:]

    if len(args) != 2:
        await message.answer(
            "Формат: `/report_test YYYY-MM-DD YYYY-MM-DD`\n"
            "Пример: `/report_test 2026-04-01 2026-04-30`",
            parse_mode="Markdown"
        )
        return

    date_start, date_end = args[0], args[1]

    # Простая валидация формата
    import re
    if not re.match(r"\d{4}-\d{2}-\d{2}", date_start) or not re.match(r"\d{4}-\d{2}-\d{2}", date_start):
        await message.answer("Неверный формат даты. Используй YYYY-MM-DD.")
        return

    try:
        async with get_db() as db:
            report = await _build_test_report(db, user_id, date_start, date_end)
        await message.answer(report, parse_mode="Markdown")
    except Exception as e:
        logger.exception(f"Ошибка /report_test: {e}")
        await message.answer("Не удалось сформировать отчёт. Проверь логи.")


async def _build_test_report(db, user_id: int, date_start: str, date_end: str) -> str:
    # Делаем date_end включительным — добавляем 1 день
    from datetime import datetime, timedelta
    end_dt = datetime.strptime(date_end, "%Y-%m-%d") + timedelta(days=1)
    date_end_exclusive = end_dt.strftime("%Y-%m-%d")

    cursor = await db.execute(
        "SELECT COUNT(*) AS total FROM sessions WHERE user_id = ? AND created_at >= ? AND created_at < ?",
        (user_id, date_start, date_end_exclusive)
    )
    row = await cursor.fetchone()
    total = row["total"] if row else 0

    cursor = await db.execute(
        """
        SELECT COUNT(*) AS done FROM sessions
        WHERE user_id = ? AND created_at >= ? AND created_at < ? AND status = 'complete'
        """,
        (user_id, date_start, date_end_exclusive)
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
        WHERE user_id = ? AND created_at >= ? AND created_at < ?
        GROUP BY period
        ORDER BY cnt DESC
        """,
        (user_id, date_start, date_end_exclusive)
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
        WHERE user_id = ? AND created_at >= ? AND created_at < ?
        GROUP BY weekday
        ORDER BY cnt DESC
        """,
        (user_id, date_start, date_end_exclusive)
    )
    by_weekday = await cursor.fetchall()

    cursor = await db.execute(
        """
        SELECT part1_data_json, part2_data_json FROM meals
        WHERE user_id = ? AND is_complete = 1
          AND timestamp_part1 >= ? AND timestamp_part1 < ?
        """,
        (user_id, date_start, date_end_exclusive)
    )
    meal_rows = await cursor.fetchall()

    hunger_vals, satisfaction_vals, sleepiness_vals = [], [], []
    for r in meal_rows:
        try:
            p1 = json.loads(r["part1_data_json"] or "{}")
            p2 = json.loads(r["part2_data_json"] or "{}")
            if "hunger_score" in p1:
                hunger_vals.append(p1["hunger_score"])
            if "sleepiness" in p1:
                sleepiness_vals.append(p1["sleepiness"])
            if "satisfaction" in p2:
                satisfaction_vals.append(p2["satisfaction"])
        except Exception:
            pass

    def avg(lst):
        return f"{sum(lst)/len(lst):.1f}" if lst else "—"

    lines = [
        f"🧪 *Тестовый отчёт*",
        f"Период: {date_start} — {date_end}",
        "",
        f"Всего запусков: {total}",
        f"Завершено полностью: {complete}",
        "",
        "📈 Средние значения:",
        f"  Голод до еды: {avg(hunger_vals)}",
        f"  Удовлетворение: {avg(satisfaction_vals)}",
        f"  Сонливость: {avg(sleepiness_vals)}",
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
