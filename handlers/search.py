# handlers/search.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback
from datetime import datetime

from ui.states import SearchStates
from ui.keyboards import trip_type_keyboard, search_results_keyboard
from services.travelpayouts import (
    search_round_trip_fixed_stay,
    search_flights_for_dates,
    get_airline_name,
)

router = Router()

# Используем .contains, чтобы избежать проблем с разными эмодзи
@router.message(F.text.contains("Найти билеты"))
async def start_search(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Откуда вылетаем? (IATA, например MOW)")
    await state.set_state(SearchStates.origin)

@router.message(SearchStates.origin)
async def set_origin(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    # Простая валидация длины IATA кода
    if len(code) != 3:
        await message.answer("⚠️ Код должен состоять из 3 букв (например, MOW). Попробуйте еще раз:")
        return
        
    await state.update_data(origin=code)
    await message.answer("Куда летим? (IATA, например DXB)")
    await state.set_state(SearchStates.destination)

@router.message(SearchStates.destination)
async def set_destination(message: Message, state: FSMContext):
    code = message.text.strip().upper()
    if len(code) != 3:
        await message.answer("⚠️ Код должен состоять из 3 букв. Попробуйте еще раз:")
        return

    await state.update_data(destination=code)
    await message.answer("Сколько пассажиров? (1–9)")
    await state.set_state(SearchStates.passengers)

@router.message(SearchStates.passengers)
async def set_passengers(message: Message, state: FSMContext):
    try:
        passengers = int(message.text)
        if not 1 <= passengers <= 9:
            raise ValueError
    except ValueError:
        await message.answer("🔢 Введите число от 1 до 9.")
        return

    await state.update_data(passengers=passengers)
    await message.answer("Выберите тип перелёта:", reply_markup=trip_type_keyboard())
    await state.set_state(SearchStates.trip_type)

# === ОБРАБОТКА ВЫБОРА "В ОДНУ СТОРОНУ" ===
@router.callback_query(F.data == "trip_one_way")
async def choose_one_way_trip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(trip_type="one_way")
    await callback.answer()
    
    calendar = SimpleCalendar()
    calendar_markup = await calendar.start_calendar()
    await callback.message.answer(
        "📅 Выберите дату вылёта:",
        reply_markup=calendar_markup
    )
    await state.set_state(SearchStates.depart_date)

# === ОБРАБОТКА ВЫБОРА "ТУДА-ОБРАТНО" ===
@router.callback_query(F.data == "trip_round")
async def choose_round_trip(callback: CallbackQuery, state: FSMContext):
    await state.update_data(trip_type="round")
    await callback.answer()

    calendar = SimpleCalendar()
    calendar_markup = await calendar.start_calendar()
    await callback.message.answer(
        "📅 Выберите дату вылёта:",
        reply_markup=calendar_markup
    )
    await state.set_state(SearchStates.depart_date)

@router.callback_query(
    SearchStates.depart_date,
    SimpleCalendarCallback.filter()
)
async def set_depart_date(
    callback: CallbackQuery,
    callback_data: SimpleCalendarCallback,
    state: FSMContext,
):
    calendar = SimpleCalendar()
    selected, depart_date = await calendar.process_selection(callback, callback_data)

    if not selected:
        return

    await state.update_data(depart_date=depart_date)
    data = await state.get_data()
    
    # 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: Если в одну сторону - ищем СРАЗУ
    if data.get("trip_type") == "one_way":
        await perform_search_one_way(callback, state, data)
        return

    # Если туда-обратно - спрашиваем вторую дату
    calendar_markup = await calendar.start_calendar()
    await callback.message.answer(
        "📅 Выберите дату возвращения:",
        reply_markup=calendar_markup
    )
    await state.set_state(SearchStates.return_date)

async def perform_search_one_way(callback: CallbackQuery, state: FSMContext, data: dict):
    """Логика поиска билетов в одну сторону"""
    await callback.message.answer(
        f"🔎 Ищу билеты {data['origin']} → {data['destination']}\n"
        f"📆 Дата: {data['depart_date']}\n"
        f"👥 Пассажиры: {data['passengers']}"
    )
    
    # Ищем билеты
    results = await search_flights_for_dates(
        origin=data['origin'],
        destination=data['destination'],
        dates=[data['depart_date']], # Можно расширить диапазон дат тут
        limit_per_day=5
    )
    
    if not results:
        await callback.message.answer("😔 Билеты не найдены.")
        await state.clear()
        return

    # Сортировка по цене
    results.sort(key=lambda x: x.get("price", 1000000))
    best_options = results[:3]
    
    text = "✈️ <b>Лучшие варианты (в одну сторону):</b>\n\n"
    for ticket in best_options:
        price = ticket.get("price") * data["passengers"]
        airline = ticket.get('airline', 'Aviasales')
        dep_time = ticket.get('departure_at', '')[:16].replace("T", " ")
        
        text += (
            f"🛫 {dep_time}\n"
            f"🏢 {airline}\n"
            f"💰 {price} RUB\n\n"
        )
        
    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            origin=data["origin"],
            dest=data["destination"],
            depart=data["depart_date"],
            ret=None, # Важно: нет возврата
            passengers=data["passengers"]
        )
    )
    await state.clear()

@router.callback_query(
    SearchStates.return_date,
    SimpleCalendarCallback.filter()
)
async def set_return_date(
    callback: CallbackQuery,
    callback_data: SimpleCalendarCallback,
    state: FSMContext,
):
    calendar = SimpleCalendar()
    selected, return_date = await calendar.process_selection(callback, callback_data)

    if not selected:
        return

    await state.update_data(return_date=return_date)
    data = await state.get_data()

    stay_days = (return_date - data["depart_date"]).days
    
    if stay_days <= 0:
        await callback.message.answer("⚠️ Дата возврата должна быть позже даты вылета! Попробуйте снова.")
        # Можно перезапустить календарь тут, но для простоты просто выходим
        return

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
        await callback.message.answer("😔 Ничего не найдено.")
        await state.clear()
        return

    text = "🔁 <b>Лучшие варианты (туда-обратно):</b>\n\n"
    for o in offers:
        out = o["outbound"]
        inn = o["inbound"]
        text += (
            f"🛫 {out['origin']} → {out['destination']} {out.get('departure_at','')[:10]}\n"
            f"🛬 {inn['origin']} → {inn['destination']} {inn.get('departure_at','')[:10]}\n"
            f"💰 <b>{o['total_price']} RUB</b>\n\n"
        )

    await callback.message.answer(
        text,
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            origin=data["origin"],
            dest=data["destination"],
            depart=data["depart_date"],
            ret=return_date,
            passengers=data["passengers"]
        )
    )
    await state.clear()