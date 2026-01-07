# ui/keyboards.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Найти билеты")],
            [KeyboardButton(text="⭐ Мои подписки")]
        ],
        resize_keyboard=True
    )

def trip_type_keyboard():
    """
    Inline keyboard для выбора типа перелёта.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➡️ В одну сторону", callback_data="trip_one_way"),
                InlineKeyboardButton(text="🔁 Туда-обратно", callback_data="trip_round"),
            ]
        ]
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )
