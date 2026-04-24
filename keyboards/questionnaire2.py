# 📄 файл: keyboards/questionnaire2.py — полная замена
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import ate_button_row


def start_q2_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать", callback_data="q2:start")]
    ])


def multiselect_q2_keyboard(
    step: int,
    options: list[tuple[str, str]],
    selected: list[str],
    has_other: bool = True,
) -> InlineKeyboardMarkup:
    rows = []
    for label, key in options:
        mark = "✅" if key in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {label}",
            callback_data=f"q:{step}:t:{key}"
        )])
    if has_other:
        rows.append([InlineKeyboardButton(
            text="⬜ Другое",
            callback_data=f"q:{step}:other"
        )])
    rows.append([InlineKeyboardButton(
        text="➡️ Далее",
        callback_data=f"q:{step}:done"
    )])
    # В опроснике 2 кнопки "Я поела" нет — еда уже съедена
    return InlineKeyboardMarkup(inline_keyboard=rows)


def satisfaction_keyboard(step: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"q:{step}:{i}")
        for i in range(1, 7)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons[:3],
        buttons[3:],
    ])


def text_q2_keyboard() -> InlineKeyboardMarkup:
    """
    Для текстовых шагов опросника 2 — пустая клавиатура.
    Пользователь просто отправляет текст сообщением.
    """
    return InlineKeyboardMarkup(inline_keyboard=[])