# 📄 файл: keyboards/common.py — полная замена
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def ate_button_row() -> list[list[InlineKeyboardButton]]:
    """
    Кнопка 'Я поела' — визуально отделена пустой строкой-разделителем.
    Возвращает два ряда: разделитель + кнопка.
    """
    return [
        [InlineKeyboardButton(text="─────────────", callback_data="noop")],
        [InlineKeyboardButton(text="🍽 Я поела", callback_data="ate:now")],
    ]


def text_step_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для шагов с текстовым вводом.
    Только кнопка 'Я поела' — без 'Готово'.
    Пользователь просто отправляет текст сообщением.
    """
    return InlineKeyboardMarkup(inline_keyboard=ate_button_row())


def scale_keyboard(step: int, scale: int) -> InlineKeyboardMarkup:
    """Универсальная шкала 1–N + кнопка 'Я поела'."""
    buttons = [
        InlineKeyboardButton(text=str(i), callback_data=f"q:{step}:{i}")
        for i in range(1, scale + 1)
    ]
    rows = [buttons[:5], buttons[5:]] if scale == 10 else [buttons[:3], buttons[3:6]]
    return InlineKeyboardMarkup(inline_keyboard=rows + ate_button_row())