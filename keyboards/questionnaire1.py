# 📄 файл: keyboards/questionnaire1.py — полная замена
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import ate_button_row


def multiselect_keyboard(
    step: int,
    options: list[tuple[str, str]],
    selected: list[str],
    has_other: bool = True,
    other_waiting: bool = False,
) -> InlineKeyboardMarkup:
    rows = []
    for label, key in options:
        mark = "✅" if key in selected else "⬜"
        rows.append([InlineKeyboardButton(
            text=f"{mark} {label}",
            callback_data=f"q:{step}:t:{key}"
        )])

    if has_other:
        other_label = "✏️ Другое (введи текст)" if other_waiting else "⬜ Другое"
        rows.append([InlineKeyboardButton(
            text=other_label,
            callback_data=f"q:{step}:other"
        )])

    rows.append([InlineKeyboardButton(
        text="➡️ Далее",
        callback_data=f"q:{step}:done"
    )])

    # Визуальный разделитель + кнопка "Я поела"
    rows.extend(ate_button_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def single_select_keyboard(
    step: int,
    options: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = []
    for label, key in options:
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"q:{step}:s:{key}"
        )])
    rows.extend(ate_button_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sleepiness_keyboard(step: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"q:{step}:{i}")
        for i in range(1, 11)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons[:5],
        buttons[5:],
        *ate_button_row(),
    ])


def hunger_keyboard(step: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"q:{step}:{i}")
        for i in range(1, 7)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons[:3],
        buttons[3:],
        *ate_button_row(),
    ])