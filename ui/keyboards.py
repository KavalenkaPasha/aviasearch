# ui/keyboards.py
from aiogram.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)

def start_inline_menu():
    """
    Главное меню (Inline) для сообщения /start.
    Заменяет старую Reply-клавиатуру.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти билеты", callback_data="start_search")],
            [InlineKeyboardButton(text="⭐ Мои подписки", callback_data="my_subs")]
        ]
    )

def navigation_menu():
    """
    Меню навигации (Reply) во время поиска.
    Появляется под строкой ввода текста.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⬅️ Назад"), KeyboardButton(text="🏠 В начало")]
        ],
        resize_keyboard=True,
        persistent=True
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

def search_results_keyboard(origin, dest, depart, ret, passengers, current_price):
    """
    Формат callback_data: sub:<price>:<origin>:<dest>:<departYYYYMMDD>:<retYYYYMMDD or 0>:<passengers>
    """
    d_val = depart
    d_str = str(d_val).replace("-", "") if d_val not in (None, "0") else "0"

    # ret может быть None / '0' / date / str; приводим к '0' или YYYYMMDD
    r_val = ret
    r_str = "0"
    if r_val not in (None, "0", ""):
        r_str = str(r_val).replace("-", "")

    # Гарантируем, что passengers всегда присутствует и — целое число
    try:
        pax_val = int(passengers)
        if pax_val < 1:
            pax_val = 1
    except Exception:
        pax_val = 1

    price_str = int(current_price) if (current_price is not None) else 0
    cb_data = f"sub:{price_str}:{origin}:{dest}:{d_str}:{r_str}:{pax_val}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 Подписаться на цену", callback_data=cb_data)]
        ]
    )

def threshold_options_keyboard(current_price, origin, dest, depart, ret, passengers):
    """
    Всегда передаём даты в компактном формате YYYYMMDD или '0' для отсутствия return.
    Это унифицирует парсинг в handlers/subscription.py.
    """
    # нормализуем вход (depart/ret могут быть date/str/'0'/None)
    def compact(d):
        if not d:
            return "0"
        s = str(d)
        # possible formats: 'YYYY-MM-DD' or 'YYYYMMDD'
        if "-" in s:
            return s.replace("-", "")
        return s

    d_comp = compact(depart)
    r_comp = compact(ret)

    cb_use = f"set_threshold_use:{int(current_price)}:{origin}:{dest}:{d_comp}:{r_comp}:{int(passengers)}"
    cb_manual = f"set_threshold_manual:{origin}:{dest}:{d_comp}:{r_comp}:{int(passengers)}"

    buttons = [
        [InlineKeyboardButton(text=f"Использовать текущую цену: {int(current_price)} RUB", callback_data=cb_use)]
    ]

    # Если даты вылета нет (d_comp == "0") — не показываем кнопку "Ввести цену вручную"
    # вместо этого даём пользователю возможность повторить поиск / выбрать даты заново.
    if d_comp != "0":
        buttons.append([InlineKeyboardButton(text="Ввести цену вручную", callback_data=cb_manual)])
    else:
        buttons.append([InlineKeyboardButton(text="Выбрать даты", callback_data="start_search")])

    buttons.append([InlineKeyboardButton(text="Отмена", callback_data="subscribe_cancel")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    return kb

def subscriptions_keyboard(subscriptions):
    buttons = []
    for sub in subscriptions:
        d_date = sub['depart_date']
        r_date = sub['return_date']
        if r_date and r_date != "0":
            arrow = "⇄"
            date_info = f"{d_date}/{r_date}"
        else:
            arrow = "→"
            date_info = f"{d_date}"
        
        # НЕ показываем цену в списке — только маршрут и даты
        text = f"{sub['origin']}{arrow}{sub['destination']} ({date_info})"
        buttons.append([
            InlineKeyboardButton(text=f"✏️ {text}", callback_data=f"edit_sub:{sub['id']}"),
            InlineKeyboardButton(text=f"❌", callback_data=f"del_sub:{sub['id']}")
        ])
    
    buttons.append([InlineKeyboardButton(text="🔙 Закрыть список", callback_data="close_subs_list")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    return kb