# 📄 файл: handlers/questionnaire1.py
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_db, get_active_session, update_session_step,
    upsert_meal_part1, mark_session_complete
)
from keyboards.questionnaire1 import (
    sleepiness_keyboard, multiselect_keyboard,
    single_select_keyboard, hunger_keyboard,
)
from keyboards.common import text_step_keyboard

logger = logging.getLogger(__name__)
router = Router()

STEPS = [
    {"key": "sleepiness",   "type": "scale10",     "text": "😴 Насколько ты сонная сейчас?\n(1 — бодрая, 10 — очень сонная)"},
    {"key": "events",       "type": "multiselect", "text": "📋 Что происходило до еды? (можно несколько)",
     "options": [("Проснулась","woke"), ("Гуляла","walk"), ("Работала","work"),
                 ("Пришла с работы","came_work"), ("Ходила в магазин","shop"),
                 ("Спорт","sport"), ("Спокойное занятие","calm")]},
    {"key": "thoughts",     "type": "text",        "text": "💭 Какие мысли сейчас крутятся в голове?"},
    {"key": "body",         "type": "multiselect", "text": "🫀 Что ощущаешь в теле?",
     "options": [("Слюноотделение","saliva"), ("Боль в желудке","stomach"),
                 ("Головокружение","dizzy"), ("Подташнивает","nausea")]},
    {"key": "feelings",     "type": "multiselect", "text": "🌈 Какие чувства сейчас?",
     "options": [("Уставшая","tired"), ("Радостная","happy"), ("Расстроенная","upset"),
                 ("Грустная","sad"), ("Веселая","fun"), ("Злая","angry"), ("Сонная","sleepy")]},
    {"key": "food_want",    "type": "multiselect", "text": "🍽 Какой еды хочется?",
     "options": [("Лёгкое","light"), ("Питательное","filling"), ("Мясо","meat")]},
    {"key": "food_plan",    "type": "text",        "text": "📝 Что собираешься съесть?"},
    {"key": "intentions",   "type": "text",        "text": "🎯 Что планируешь делать после еды?"},
    {"key": "reason",       "type": "single",      "text": "❓ Почему хочется есть сейчас?",
     "options": [("Голод","hunger"), ("Расстроена","upset"), ("Скучно","bored"), ("Другое","other")]},
    {"key": "hunger_score", "type": "scale6",      "text": "🔢 Оцени голод.\n(1 — совсем не голодна, 6 — очень голодна)"},
]


async def send_step(message: Message, session, step_index: int):
    if step_index >= len(STEPS):
        await _finish_q1(message, session)
        return

    step = STEPS[step_index]
    answers = json.loads(session["answers_json"] or "{}")

    if step["type"] == "scale10":
        await message.answer(step["text"], reply_markup=sleepiness_keyboard(step_index))

    elif step["type"] == "scale6":
        await message.answer(step["text"], reply_markup=hunger_keyboard(step_index))

    elif step["type"] == "multiselect":
        selected = answers.get(step["key"], [])
        await message.answer(
            step["text"],
            reply_markup=multiselect_keyboard(
                step=step_index,
                options=step["options"],
                selected=selected,
            )
        )

    elif step["type"] == "single":
        await message.answer(
            step["text"],
            reply_markup=single_select_keyboard(step_index, step["options"])
        )

    elif step["type"] == "text":
        await message.answer(
            step["text"] + "\n\n_Напиши ответ и отправь сообщением_",
            reply_markup=text_step_keyboard(),
            parse_mode="Markdown"
        )


async def _finish_q1(message: Message, session):
    user_id = session["user_id"]
    session_id = session["id"]
    answers = json.loads(session["answers_json"] or "{}")

    async with get_db() as db:
        await upsert_meal_part1(db, user_id, session_id, json.dumps(answers, ensure_ascii=False))
        await update_session_step(db, session_id, "waiting_part2", json.dumps(answers, ensure_ascii=False))

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Я поела", callback_data="ate:now")]
    ])
    await message.answer(
        "✨ Первая часть готова. Спасибо!\n\n"
        "Когда поешь — нажми кнопку ниже.\n"
        "Или я напомню через 30 минут.",
        reply_markup=keyboard
    )


# ---------------------------------------------------------------------------
# Кнопка "Я поела" — доступна на любом шаге q1
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ate:now")
async def on_ate(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Активная сессия не найдена.", show_alert=True)
                return

            answers = json.loads(session["answers_json"] or "{}")
            session_id = session["id"]

            await upsert_meal_part1(
                db, user_id, session_id,
                json.dumps(answers, ensure_ascii=False)
            )
            await update_session_step(
                db, session_id, "q2_step_0",
                json.dumps(answers, ensure_ascii=False)
            )

        from keyboards.questionnaire2 import start_q2_keyboard
        await callback.message.answer(
            "🍽 Отлично! Давай заполним второй опрос.",
            reply_markup=start_q2_keyboard()
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка в on_ate: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)


# ---------------------------------------------------------------------------
# Callback-кнопки опросника 1 (step_index 0–19)
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("q:"))
async def on_q1_callback(callback: CallbackQuery):
    from handlers.questionnaire2 import send_q2_step, STEPS_Q2
    parts = callback.data.split(":")
    try:
        step_index = int(parts[1])
    except (IndexError, ValueError):
        await callback.answer()
        return

    action = parts[2] if len(parts) > 2 else ""
    user_id = callback.from_user.id

    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Сессия не найдена.", show_alert=True)
                return

            current = session["current_step"] or ""
            answers = json.loads(session["answers_json"] or "{}")

            # ---------------------------------------------------------------
            # Опросник 2 (offset 20+)
            # ---------------------------------------------------------------
            if step_index >= 20:
                if not current.startswith("q2_step_"):
                    await callback.answer()
                    return

                q2_index = step_index - 20
                step = STEPS_Q2[q2_index] if q2_index < len(STEPS_Q2) else None
                if not step:
                    await callback.answer()
                    return

                if action == "t" and len(parts) > 3:
                    key = parts[3]
                    field = step["key"]
                    selected = answers.get(field, [])
                    if key in selected:
                        selected.remove(key)
                    else:
                        selected.append(key)
                    answers[field] = selected
                    await update_session_step(
                        db, session["id"], f"q2_step_{q2_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    from keyboards.questionnaire2 import multiselect_q2_keyboard
                    await callback.message.edit_reply_markup(
                        reply_markup=multiselect_q2_keyboard(
                            step=step_index,
                            options=step["options"],
                            selected=selected,
                        )
                    )
                    await callback.answer()
                    return

                if action == "other":
                    answers[f"{step['key']}_other_pending"] = True
                    await update_session_step(
                        db, session["id"], f"q2_step_{q2_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    await callback.message.answer("✏️ Напиши своё — я добавлю к ответу.")
                    await callback.answer()
                    return

                if action == "done":
                    answers.pop(f"{step['key']}_other_pending", None)
                    next_index = q2_index + 1
                    await update_session_step(
                        db, session["id"], f"q2_step_{next_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                    await send_q2_step(callback.message, updated, next_index)
                    await callback.answer()
                    return

                if action.isdigit():
                    answers[step["key"]] = int(action)
                    next_index = q2_index + 1
                    await update_session_step(
                        db, session["id"], f"q2_step_{next_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                    await send_q2_step(callback.message, updated, next_index)
                    await callback.answer()
                    return

                await callback.answer()
                return

            # ---------------------------------------------------------------
            # Опросник 1 (0–19)
            # ---------------------------------------------------------------
            if current.startswith("q2") or current == "waiting_part2":
                await callback.answer()
                return

            step = STEPS[step_index] if step_index < len(STEPS) else None
            if not step:
                await callback.answer()
                return

            if action == "t" and len(parts) > 3:
                key = parts[3]
                field = step["key"]
                selected = answers.get(field, [])
                if key in selected:
                    selected.remove(key)
                else:
                    selected.append(key)
                answers[field] = selected
                await update_session_step(
                    db, session["id"], f"q1_step_{step_index}",
                    json.dumps(answers, ensure_ascii=False)
                )
                await callback.message.edit_reply_markup(
                    reply_markup=multiselect_keyboard(
                        step=step_index,
                        options=step["options"],
                        selected=selected,
                    )
                )
                await callback.answer()
                return

            if action == "other":
                answers[f"{step['key']}_other_pending"] = True
                await update_session_step(
                    db, session["id"], f"q1_step_{step_index}",
                    json.dumps(answers, ensure_ascii=False)
                )
                await callback.message.answer("✏️ Напиши своё — я добавлю к ответу.")
                await callback.answer()
                return

            if action == "done":
                answers.pop(f"{step['key']}_other_pending", None)
                next_index = step_index + 1
                await update_session_step(
                    db, session["id"], f"q1_step_{next_index}",
                    json.dumps(answers, ensure_ascii=False)
                )
                updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                await send_step(callback.message, updated, next_index)
                await callback.answer()
                return

            if action == "s" and len(parts) > 3:
                key = parts[3]
                answers[step["key"]] = key
                next_index = step_index + 1
                await update_session_step(
                    db, session["id"], f"q1_step_{next_index}",
                    json.dumps(answers, ensure_ascii=False)
                )
                updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                await send_step(callback.message, updated, next_index)
                await callback.answer()
                return

            if action.isdigit():
                answers[step["key"]] = int(action)
                next_index = step_index + 1
                await update_session_step(
                    db, session["id"], f"q1_step_{next_index}",
                    json.dumps(answers, ensure_ascii=False)
                )
                updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                await send_step(callback.message, updated, next_index)
                await callback.answer()
                return

        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка в on_q1_callback: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)

@router.message(F.text & ~F.text.startswith("/"))
async def on_text_input(message: Message):
    user_id = message.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                return

            current = session["current_step"] or ""
            answers = json.loads(session["answers_json"] or "{}")

            # --- Опросник 1 ---
            if current.startswith("q1_step_"):
                try:
                    step_index = int(current.replace("q1_step_", ""))
                except ValueError:
                    return
                if step_index >= len(STEPS):
                    return
                step = STEPS[step_index]

                if step["type"] == "text":
                    answers[step["key"]] = message.text
                    next_index = step_index + 1
                    await update_session_step(
                        db, session["id"], f"q1_step_{next_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                    await send_step(message, updated, next_index)
                    return

                if answers.get(f"{step['key']}_other_pending"):
                    field = step["key"]
                    selected = answers.get(field, [])
                    selected.append(message.text)
                    answers[field] = selected
                    answers.pop(f"{field}_other_pending", None)
                    await update_session_step(
                        db, session["id"], f"q1_step_{step_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    await message.answer("✅ Добавила! Выбери ещё или нажми «Далее».")
                    return

            # --- Опросник 2 ---
            elif current.startswith("q2_step_"):
                from handlers.questionnaire2 import send_q2_step, STEPS_Q2
                try:
                    step_index = int(current.replace("q2_step_", ""))
                except ValueError:
                    return
                if step_index >= len(STEPS_Q2):
                    return
                step = STEPS_Q2[step_index]

                if step["type"] == "text":
                    answers[step["key"]] = message.text
                    next_index = step_index + 1
                    await update_session_step(
                        db, session["id"], f"q2_step_{next_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    updated = {**dict(session), "answers_json": json.dumps(answers, ensure_ascii=False)}
                    await send_q2_step(message, updated, next_index)
                    return

                if answers.get(f"{step['key']}_other_pending"):
                    field = step["key"]
                    selected = answers.get(field, [])
                    selected.append(message.text)
                    answers[field] = selected
                    answers.pop(f"{field}_other_pending", None)
                    await update_session_step(
                        db, session["id"], f"q2_step_{step_index}",
                        json.dumps(answers, ensure_ascii=False)
                    )
                    await message.answer("✅ Добавила! Выбери ещё или нажми «Далее».")
                    return

    except Exception as e:
        logger.exception(f"Ошибка в on_text_input: {e}")