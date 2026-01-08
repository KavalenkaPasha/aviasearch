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
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➡️ В одну сторону", callback_data="trip_one_way"),
                InlineKeyboardButton(text="🔁 Туда-обратно", callback_data="trip_round"),
            ]
        ]
    )

def search_results_keyboard(origin, dest, depart, ret, passengers):
    """Кнопка подписки. Если ret=None, ставим '0'."""
    d_str = str(depart).replace("-", "")
    
    if ret:
        r_str = str(ret).replace("-", "")
    else:
        r_str = "0" # Маркер отсутствия возврата

    cb_data = f"sub:{origin}:{dest}:{d_str}:{r_str}:{passengers}"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Подписаться на цену", callback_data=cb_data)]
        ]
    )

def subscriptions_keyboard(subscriptions):
    buttons = []
    for sub in subscriptions:
        d_date = sub['depart_date']
        r_date = sub['return_date']
        
        # Красивое отображение
        if r_date and r_date != "0":
            arrow = "⇄"
            date_info = f"{d_date}/{r_date}"
        else:
            arrow = "→"
            date_info = f"{d_date}"
            
        text = f"{sub['origin']}{arrow}{sub['destination']} ({date_info})"
        buttons.append([
            InlineKeyboardButton(text=f"❌ {text}", callback_data=f"del_sub:{sub['id']}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)