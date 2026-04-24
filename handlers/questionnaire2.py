# 📄 файл: handlers/questionnaire2.py
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_db, get_active_session, update_session_step,
    save_meal_part2, mark_session_complete
)
from keyboards.questionnaire2 import (
    multiselect_q2_keyboard, satisfaction_keyboard, text_q2_keyboard
)

logger = logging.getLogger(__name__)
router = Router()

STEPS_Q2 = [
    {"key": "thoughts_after",   "type": "text",        "text": "💭 Какие мысли сейчас?"},
    {"key": "feelings_after",   "type": "multiselect", "text": "🌈 Какие чувства сейчас?",
     "options": [("Уставшая","tired"), ("Радостная","happy"), ("Расстроенная","upset"),
                 ("Грустная","sad"), ("Веселая","fun"), ("Злая","angry"), ("Сонная","sleepy")]},
    {"key": "intentions_after", "type": "text",        "text": "🎯 Что планируешь делать сейчас?"},
    {"key": "satisfaction",     "type": "scale6",      "text": "🔢 Насколько удовлетворена?\n(1 — совсем нет, 6 — полностью)"},
    {"key": "body_after",       "type": "multiselect", "text": "🫀 Что ощущаешь в теле после еды?",
     "options": [("Сытость","full"), ("Тяжесть","heavy"), ("Голод","hungry")]},
]

Q2_STEP_OFFSET = 20


async def send_q2_step(message: Message, session, step_index: int):
    if step_index >= len(STEPS_Q2):
        await _finish_q2(message, session)
        return

    step = STEPS_Q2[step_index]
    answers = json.loads(session["answers_json"] or "{}")
    cb_step = step_index + Q2_STEP_OFFSET

    if step["type"] == "text":
        await message.answer(
            step["text"] + "\n\n_Напиши ответ и отправь сообщением_",
            reply_markup=text_q2_keyboard(),
            parse_mode="Markdown"
        )

    elif step["type"] == "multiselect":
        selected = answers.get(step["key"], [])
        await message.answer(
            step["text"],
            reply_markup=multiselect_q2_keyboard(
                step=cb_step,
                options=step["options"],
                selected=selected,
            )
        )

    elif step["type"] == "scale6":
        await message.answer(
            step["text"],
            reply_markup=satisfaction_keyboard(cb_step)
        )


async def _finish_q2(message: Message, session):
    session_id = session["id"]
    answers = json.loads(session["answers_json"] or "{}")

    part2_keys = {s["key"] for s in STEPS_Q2}
    part2_data = {k: v for k, v in answers.items() if k in part2_keys}

    async with get_db() as db:
        await save_meal_part2(
            db, session_id,
            json.dumps(part2_data, ensure_ascii=False)
        )
        await mark_session_complete(db, session_id)

    await message.answer(
        "✨ Всё записала. Спасибо, что прошла оба опроса.\n\n"
        "Данные сохранены — выгрузить их можно командой /export."
    )
# Сразу показываем кнопку для нового цикла
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await message.answer(
        "Я здесь, если понадоблюсь 🤍",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💙 мне грустно", callback_data="sad:start")]
        ])
    )


# ---------------------------------------------------------------------------
# Запуск опросника 2
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "q2:start")
async def on_q2_start(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Сессия не найдена.", show_alert=True)
                return
            await update_session_step(
                db, session["id"], "q2_step_0",
                session["answers_json"] or "{}"
            )
            updated = {**dict(session), "current_step": "q2_step_0"}
            await send_q2_step(callback.message, updated, step_index=0)
            await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в on_q2_start: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)


# ---------------------------------------------------------------------------
# Callback-кнопки опросника 2 (offset 20+)
# ---------------------------------------------------------------------------