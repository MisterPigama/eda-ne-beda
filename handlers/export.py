# 📄 файл: handlers/export.py
import csv
import io
import json
import logging
from aiogram import Router
from aiogram.types import Message, BufferedInputFile
from aiogram.filters import Command

from database import get_db

logger = logging.getLogger(__name__)
router = Router()

# ---------------------------------------------------------------------------
# Человекочитаемые метки для экспорта
# ---------------------------------------------------------------------------

FIELD_LABELS = {
    "sleepiness":        "Сонливость (1-10)",
    "events":            "События до еды",
    "thoughts":          "Мысли до еды",
    "body":              "Ощущения в теле до",
    "feelings":          "Чувства до еды",
    "food_want":         "Хотелось еды",
    "food_plan":         "Что планировала съесть",
    "intentions":        "Намерения после еды",
    "reason":            "Причина еды",
    "hunger_score":      "Оценка голода (1-6)",
    "thoughts_after":    "Мысли после еды",
    "feelings_after":    "Чувства после еды",
    "intentions_after":  "Намерения сейчас",
    "satisfaction":      "Удовлетворение (1-6)",
    "body_after":        "Ощущения после еды",
}

OPTION_LABELS = {
    "woke": "Проснулась", "walk": "Гуляла", "work": "Работала",
    "came_work": "Пришла с работы", "shop": "Ходила в магазин",
    "sport": "Спорт", "calm": "Спокойное занятие",
    "saliva": "Слюноотделение", "stomach": "Боль в желудке",
    "dizzy": "Головокружение", "nausea": "Подташнивает",
    "tired": "Уставшая", "happy": "Радостная", "upset": "Расстроенная",
    "sad": "Грустная", "fun": "Весёлая", "angry": "Злая", "sleepy": "Сонная",
    "light": "Лёгкое", "filling": "Питательное", "meat": "Мясо",
    "hunger": "Голод", "bored": "Скучно", "other": "Другое",
    "full": "Сытость", "heavy": "Тяжесть",
}


def _decode_value(value) -> str:
    """Декодирует значение поля в читаемую строку."""
    if isinstance(value, list):
        return ", ".join(OPTION_LABELS.get(v, v) for v in value)
    if isinstance(value, str):
        return OPTION_LABELS.get(value, value)
    return str(value) if value is not None else ""


# ---------------------------------------------------------------------------
# /export — полная история в CSV
# ---------------------------------------------------------------------------

@router.message(Command("export"))
async def cmd_export(message: Message):
    user_id = message.from_user.id
    try:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT
                    m.id,
                    m.timestamp_part1,
                    m.timestamp_part2,
                    m.part1_data_json,
                    m.part2_data_json,
                    m.is_complete,
                    s.status AS session_status
                FROM meals m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.user_id = ?
                ORDER BY m.timestamp_part1 ASC
                """,
                (user_id,)
            )
            rows = await cursor.fetchall()

        if not rows:
            await message.answer("Пока нет сохранённых данных для экспорта.")
            return

        output = io.StringIO()
        # BOM для корректного открытия в Excel
        output.write("\ufeff")

        fieldnames = (
            ["id", "дата_опрос1", "дата_опрос2", "статус_сессии", "завершено"]
            + [FIELD_LABELS.get(k, k) for k in FIELD_LABELS.keys()]
        )

        writer = csv.DictWriter(
            output,
            fieldnames=fieldnames,
            extrasaction="ignore",
            lineterminator="\n"
        )
        writer.writeheader()

        for row in rows:
            part1 = json.loads(row["part1_data_json"] or "{}")
            part2 = json.loads(row["part2_data_json"] or "{}")
            combined = {**part1, **part2}

            csv_row = {
                "id":              row["id"],
                "дата_опрос1":     row["timestamp_part1"] or "",
                "дата_опрос2":     row["timestamp_part2"] or "",
                "статус_сессии":   row["session_status"] or "",
                "завершено":       "да" if row["is_complete"] else "нет",
            }
            for key, label in FIELD_LABELS.items():
                csv_row[label] = _decode_value(combined.get(key))

            writer.writerow(csv_row)

        csv_bytes = output.getvalue().encode("utf-8-sig")
        file = BufferedInputFile(csv_bytes, filename="history.csv")

        await message.answer_document(
            file,
            caption=(
                f"📊 Экспорт данных: {len(rows)} записей.\n"
                "Файл можно открыть в Excel или передать специалисту."
            )
        )
        logger.info(f"Экспорт выполнен для user {user_id}: {len(rows)} записей")

    except Exception as e:
        logger.exception(f"Ошибка экспорта для user {user_id}: {e}")
        await message.answer(
            "Не удалось создать файл экспорта. "
            "Попробуй позже или обратись к администратору."
        )