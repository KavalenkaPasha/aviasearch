# handlers/search.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import datetime, timedelta

from ui.states import SearchStates
from ui.keyboards import (
    trip_type_keyboard, 
    search_results_keyboard, 
    navigation_menu, 
    start_inline_menu
)
from services.travelpayouts import (
    search_round_trip_fixed_stay,
    search_flights_for_dates,
    get_airline_name,
)

router = Router()

# --- ОБРАБОТКА НАВИГАЦИИ (Глобальная для этого роутера) ---

@router.message(F.text == "🏠 В начало")
async def home_button(message: Message, state: FSMContext):
    """Сброс всего и возврат к стартовому меню"""
    await state.clear()
    await message.answer(
        "🏠 Вы вернулись в главное меню.", 
        reply_markup=ReplyKeyboardRemove()
    )
    await message.answer(
        "Выберите действие:",
        reply_markup=start_inline_menu()
    )

@router.message(F.text == "⬅️ Назад")
async def back_button(message: Message, state: FSMContext):
    """Логика возврата на шаг назад"""
    current_state = await state.get_state()
    
    if current_state == SearchStates.destination:
        await message.answer("Откуда вылетаем? (IATA, например MOW)", reply_markup=navigation_menu())
        await state.set_state(SearchStates.origin)
        
    elif current_state == SearchStates.passengers:
        data = await state.get_data()
        origin = data.get('origin', '???')
        await message.answer(f"Вылет из: {origin}\nКуда летим? (IATA, например DXB)", reply_markup=navigation_menu())
        await state.set_state(SearchStates.destination)
        
    elif current_state == SearchStates.trip_type:
        await message.answer("Сколько пассажиров? (1–9)", reply_markup=navigation_menu())
        await state.set_state(SearchStates.passengers)
        
    elif current_state == SearchStates.depart_date:
        await message.answer("Выберите тип перелёта:", reply_markup=trip_type_keyboard())
        await state.set_state(SearchStates.trip_type)
        
    elif current_state == SearchStates.return_date:
        calendar = SimpleCalendar()
        await message.answer("📅 Выберите дату вылёта:", reply_markup=await calendar.start_calendar())
        await state.set_state(SearchStates.depart_date)
        
    elif current_state == SearchStates.origin:
        await home_button(message, state)
    else:
        await home_button(message, state)

# --- НАЧАЛО ПОИСКА ---

@router.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.answer(
        "🛫 Начинаем поиск!\n\nОткуда вылетаем? (Код IATA, например MOW или LED)",
        reply_markup=navigation_menu()
    )
    await state.set_state(SearchStates.origin)

# --- ШАГИ ПОИСКА ---

@router.message(SearchStates.origin)
async def set_origin(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if len(code) != 3:
        await message.answer("⚠️ Код должен состоять из 3 букв (например, MOW). Попробуйте еще раз:", reply_markup=navigation_menu())
        return
    
    await state.update_data(origin=code)
    await message.answer(f"✅ Откуда: {code}\n\nКуда летим? (IATA, например DXB)", reply_markup=navigation_menu())
    await state.set_state(SearchStates.destination)

@router.message(SearchStates.destination)
async def set_destination(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if len(code) != 3:
        await message.answer("⚠️ Код должен состоять из 3 букв. Попробуйте еще раз:", reply_markup=navigation_menu())
        return
    await state.update_data(destination=code)
    await message.answer("Сколько пассажиров? (1–9)", reply_markup=navigation_menu())
    await state.set_state(SearchStates.passengers)

@router.message(SearchStates.passengers)
async def set_passengers(message: Message, state: FSMContext):
    try:
        count = int(message.text.strip())
        if not (1 <= count <= 9):
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите число от 1 до 9:", reply_markup=navigation_menu())
        return

    # ВАЖНО: сохраняем число, а не функцию!
    await state.update_data(passengers=count)
    
    await message.answer(
        f"👥 Пассажиров: {count}\nВыберите тип перелёта:", 
        reply_markup=trip_type_keyboard() 
    )
    await state.set_state(SearchStates.trip_type)

@router.callback_query(F.data == "trip_one_way")
async def choose_one_way(callback: CallbackQuery, state: FSMContext):
    await state.update_data(trip_type="one_way")
    await callback.answer()
    calendar = SimpleCalendar()
    await callback.message.answer("Открываю календарь...", reply_markup=navigation_menu())
    await callback.message.answer("📅 Выберите дату вылёта:", reply_markup=await calendar.start_calendar())
    await state.set_state(SearchStates.depart_date)

@router.callback_query(F.data == "trip_round")
async def choose_round_trip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(trip_type="round")
    await callback.answer()
    
    calendar = SimpleCalendar()
    await callback.message.answer("📅 Выберите дату вылёта:", reply_markup=await calendar.start_calendar())
    await state.set_state(SearchStates.depart_date)

@router.callback_query(SearchStates.depart_date, SimpleCalendarCallback.filter())
async def set_depart_date(callback: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    calendar = SimpleCalendar()
    selected, depart_date = await calendar.process_selection(callback, callback_data)
    
    if not selected:
        return

    await state.update_data(depart_date=depart_date)
    data = await state.get_data()

    if data.get("trip_type") == "one_way":
        await perform_search_one_way(callback, state, data)
        return

    await callback.message.answer("📅 Выберите дату возвращения:", reply_markup=await calendar.start_calendar())
    await state.set_state(SearchStates.return_date)

@router.callback_query(SearchStates.return_date, SimpleCalendarCallback.filter())
async def set_return_date(callback: CallbackQuery, callback_data: SimpleCalendarCallback, state: FSMContext):
    calendar = SimpleCalendar()
    selected, return_date = await calendar.process_selection(callback, callback_data)
    if not selected:
        return
        
    await state.update_data(return_date=return_date)
    data = await state.get_data()
    
    if data["depart_date"] > return_date:
        await callback.message.answer("⚠️ Дата возврата не может быть раньше вылета! Выберите заново:", reply_markup=await calendar.start_calendar())
        return

    stay_days = (return_date - data["depart_date"]).days
    
    await callback.message.answer(
        f"🔎 Ищу билеты {data['origin']} → {data['destination']}\n"
        f"📆 Туда-обратно ({stay_days} дней)\n"
    )
    
    offers = await search_round_trip_fixed_stay(
        origin=data["origin"],
        destination=data["destination"],
        depart_date=data["depart_date"],
        return_date=return_date,
        passengers=data["passengers"],
        days_flex=5,
    )
    
    
    if not offers:
        await callback.message.answer("😔 Ничего не найдено.", reply_markup=ReplyKeyboardRemove())
        await callback.message.answer("Главное меню:", reply_markup=start_inline_menu())
        return

    offers.sort(key=lambda x: x["total_price"])
    current_price = offers[0]["total_price"]
    
    text = "🔁 <b>Лучшие варианты (туда-обратно):</b>\n\n"
    for o in offers[:3]:
        out = o["outbound"]
        inn = o["inbound"]
        airline_name = get_airline_name(out.get('airline', ''))
        
        text += (
            f"🛫 {out['origin']} → {out['destination']} {out.get('departure_at','')[:10]}\n"
            f"🛬 {inn['origin']} → {inn['destination']} {inn.get('departure_at','')[:10]}\n"
            f"🏢 {airline_name}\n"
            f"💰 <b>{o['total_price']} RUB</b>\n\n"
        )
        
    await callback.message.answer("✅ Результаты поиска:", reply_markup=ReplyKeyboardRemove())
    
    await state.update_data(sub_params={
        "origin": data["origin"],
        "destination": data["destination"],
        "depart": data["depart_date"],
        "return": return_date,
        "passengers": data["passengers"]
    })

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            origin=data["origin"],
            dest=data["destination"],
            depart=data["depart_date"],
            ret=return_date,
            passengers=data["passengers"],
            current_price=current_price
        )
    )


async def perform_search_one_way(callback: CallbackQuery, state: FSMContext, data: dict):
    from datetime import timedelta

    await callback.message.answer(
        f"🔎 Ищу билеты {data['origin']} → {data['destination']}\n"
        f"📆 Дата: {data['depart_date']} ± 7 дней\n"
        f"👥 Пассажиры: {data['passengers']}"
    )

    base_date = data["depart_date"]
    search_dates = [base_date + timedelta(days=d) for d in range(-7, 8)]

    results = await search_flights_for_dates(
        origin=data['origin'],
        destination=data['destination'],
        dates=search_dates,
        limit_per_day=5
    )
    
    if not results:
        await callback.message.answer("😔 Билеты не найдены.", reply_markup=ReplyKeyboardRemove())
        await callback.message.answer("Главное меню:", reply_markup=start_inline_menu())
        return

    results.sort(key=lambda x: float(x.get("price", 999999)))

    best = results[0]
    raw_price = float(best.get("price", 0))
    current_price = int(raw_price * data["passengers"]) if raw_price > 0 else 0

    await callback.message.answer("✅ Результаты поиска:", reply_markup=ReplyKeyboardRemove())

    text = "✈️ <b>Лучшие варианты (в одну сторону):</b>\n\n"
    for ticket in results[:3]:
        price = int(float(ticket.get("price", 0)) * data["passengers"])
        airline_name = get_airline_name(ticket.get('airline', ''))
        dep_time = ticket.get('departure_at', '')[:16].replace("T", " ")
        text += (
            f"🛫 {dep_time}\n"
            f"🏢 {airline_name}\n"
            f"💰 {price} RUB\n\n"
        )

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            origin=data["origin"],
            dest=data["destination"],
            depart=data["depart_date"],
            ret=None,
            passengers=data["passengers"],
            current_price=current_price
        )
    )