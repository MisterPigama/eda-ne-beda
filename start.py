# 📄 файл: handlers/start.py
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

from database import get_db, get_active_session, create_session, update_session_step

logger = logging.getLogger(__name__)
router = Router()

SUPPORT_MESSAGE = (
    "Слышу тебя. 🤍\n"
    "Хорошо, что ты здесь.\n\n"
    "Давай пройдём небольшой опрос — это займёт несколько минут."
)


def choice_keyboard() -> InlineKeyboardMarkup:
    """Две кнопки вместо одной 'мне грустно'."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍽 Планирую поесть", callback_data="flow:plan")],
        [InlineKeyboardButton(text="✅ Уже поела", callback_data="flow:ate")],
    ])


def continue_or_restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Продолжить", callback_data="continue_flow")],
        [InlineKeyboardButton(text="🔄 Начать заново", callback_data="restart_flow")],
    ])


def start_q1_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать опрос", callback_data="q1:start")]
    ])


@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    try:
        async with get_db() as db:
            existing = await get_active_session(db, user_id)
        if existing:
            await message.answer(
                "У тебя есть незавершённый опрос.\n"
                "Продолжить с того места или начать заново?",
                reply_markup=continue_or_restart_keyboard()
            )
        else:
            await message.answer(
                "Привет 🤍\nЯ здесь, когда тебе нужна поддержка.\n\n"
                "Что происходит?",
                reply_markup=choice_keyboard()
            )
    except Exception as e:
        logger.exception(f"Ошибка в cmd_start: {e}")


@router.callback_query(F.data == "flow:plan")
async def on_flow_plan(callback: CallbackQuery):
    """Полный сценарий — опросник 1 + опросник 2."""
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            existing = await get_active_session(db, user_id)
            if existing:
                await callback.answer()
                await callback.message.answer(
                    "У тебя есть незавершённый опрос.\n"
                    "Продолжить с того места или начать заново?",
                    reply_markup=continue_or_restart_keyboard()
                )
                return
            await create_session(db, user_id)

        await callback.message.answer(SUPPORT_MESSAGE, reply_markup=start_q1_keyboard())
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка в on_flow_plan: {e}")
        await callback.answer("Что-то пошло не так. Попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data == "flow:ate")
async def on_flow_ate(callback: CallbackQuery):
    """Только опросник 2 — еда уже была."""
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            existing = await get_active_session(db, user_id)
            if existing:
                await callback.answer()
                await callback.message.answer(
                    "У тебя есть незавершённый опрос.\n"
                    "Продолжить с того места или начать заново?",
                    reply_markup=continue_or_restart_keyboard()
                )
                return

            # Создаём сессию и сразу переводим на q2
            session_id = await create_session(db, user_id)
            await update_session_step(db, session_id, "q2_step_0", "{}")

        from keyboards.questionnaire2 import start_q2_keyboard
        await callback.message.answer(
            "Хорошо. Давай заполним опрос — это займёт пару минут.",
            reply_markup=start_q2_keyboard()
        )
        await callback.answer()

    except Exception as e:
        logger.exception(f"Ошибка в on_flow_ate: {e}")
        await callback.answer("Что-то пошло не так. Попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data == "q1:start")
async def on_q1_start(callback: CallbackQuery):
    from handlers.questionnaire1 import send_step
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Сессия не найдена. Начни заново.", show_alert=True)
                return
            await send_step(callback.message, session, step_index=0)
            await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в on_q1_start: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data == "continue_flow")
async def on_continue_flow(callback: CallbackQuery):
    from handlers.questionnaire1 import send_step
    from handlers.questionnaire2 import send_q2_step
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Сессия не найдена.", show_alert=True)
                return

        current = session["current_step"] or "q1_step_0"

        if current.startswith("q1_step_"):
            step_index = int(current.replace("q1_step_", "")) if current.replace("q1_step_", "").isdigit() else 0
            await send_step(callback.message, session, step_index)
        elif current == "waiting_part2":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🍽 Я поела", callback_data="ate:now")]
            ])
            await callback.message.answer("Ты уже заполнила первый опрос.\nКогда поешь — нажми кнопку:", reply_markup=keyboard)
        elif current.startswith("q2_step_"):
            step_index = int(current.replace("q2_step_", "")) if current.replace("q2_step_", "").isdigit() else 0
            await send_q2_step(callback.message, session, step_index)
        else:
            await callback.message.answer("Не могу определить шаг. Начнём сначала?", reply_markup=start_q1_keyboard())

        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в on_continue_flow: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data == "restart_flow")
async def on_restart_flow(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if session:
                await db.execute(
                    "UPDATE sessions SET status = 'aborted' WHERE id = ?",
                    (session["id"],)
                )
                await db.commit()
            await create_session(db, user_id)
        await callback.message.answer(SUPPORT_MESSAGE, reply_markup=start_q1_keyboard())
        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в on_restart_flow: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)


@router.callback_query(F.data == "noop")
async def on_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "resume_survey")
async def on_resume_survey(callback: CallbackQuery):
    from handlers.questionnaire1 import send_step
    from handlers.questionnaire2 import send_q2_step
    user_id = callback.from_user.id
    try:
        async with get_db() as db:
            session = await get_active_session(db, user_id)
            if not session:
                await callback.answer("Сессия истекла.", show_alert=True)
                return

        current = session["current_step"] or "q1_step_0"

        if current.startswith("q1_step_"):
            step_index = int(current.replace("q1_step_", "")) if current.replace("q1_step_", "").isdigit() else 0
            await send_step(callback.message, session, step_index)
        elif current.startswith("q2_step_"):
            step_index = int(current.replace("q2_step_", "")) if current.replace("q2_step_", "").isdigit() else 0
            await send_q2_step(callback.message, session, step_index)
        elif current == "waiting_part2":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🍽 Я поела", callback_data="ate:now")]
            ])
            await callback.message.answer("Когда поешь — нажми кнопку:", reply_markup=keyboard)

        await callback.answer()
    except Exception as e:
        logger.exception(f"Ошибка в on_resume_survey: {e}")
        await callback.answer("Ошибка. Попробуй ещё раз.", show_alert=True)