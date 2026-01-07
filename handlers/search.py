# handlers/search.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from aiogram_calendar import SimpleCalendar, SimpleCalendarCallback

from ui.states import SearchStates
from ui.keyboards import trip_type_keyboard
from services.travelpayouts import (
    search_round_trip_fixed_stay,
    search_flights_for_dates,
)

router = Router()


@router.message(F.text == "🔍 Найти билеты")
async def start_search(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Откуда вылетаем? (IATA, например MOW)")
    await state.set_state(SearchStates.origin)


@router.message(SearchStates.origin)
async def set_origin(message: Message, state: FSMContext):
    await state.update_data(origin=message.text.strip().upper())
    await message.answer("Куда летим? (IATA, например DPS)")
    await state.set_state(SearchStates.destination)


@router.message(SearchStates.destination)
async def set_destination(message: Message, state: FSMContext):
    await state.update_data(destination=message.text.strip().upper())
    await message.answer("Сколько пассажиров? (1–9)")
    await state.set_state(SearchStates.passengers)


@router.message(SearchStates.passengers)
async def set_passengers(message: Message, state: FSMContext):
    try:
        passengers = int(message.text)
        if not 1 <= passengers <= 9:
            raise ValueError
    except ValueError:
        await message.answer("Введите число от 1 до 9.")
        return

    await state.update_data(passengers=passengers)
    await message.answer("Выберите тип перелёта:", reply_markup=trip_type_keyboard())
    await state.set_state(SearchStates.trip_type)


@router.callback_query(F.data == "trip_round")
async def choose_round_trip(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    calendar = SimpleCalendar()
    # start_calendar — асинхронный метод в этой версии, поэтому await
    calendar_markup = await calendar.start_calendar()
    await callback.message.answer(
        "Выберите дату вылёта:",
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

    calendar_markup = await calendar.start_calendar()
    await callback.message.answer(
        "Выберите дату возвращения:",
        reply_markup=calendar_markup
    )

    await state.set_state(SearchStates.return_date)


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

    data = await state.get_data()
    await state.update_data(return_date=return_date)

    # фиксированная длительность
    stay_days = (return_date - data["depart_date"]).days

    await callback.message.answer(
        f"🔎 Ищу билеты {data['origin']} → {data['destination']}\n"
        f"👥 Пассажиры: {data['passengers']}\n"
        f"📆 Поездка: {stay_days} дней (фиксировано)\n"
        f"±7 дней от даты вылёта"
    )

    offers = await search_round_trip_fixed_stay(
        origin=data["origin"],
        destination=data["destination"],
        depart_date=data["depart_date"],
        return_date=return_date,
        passengers=data["passengers"],
        days_flex=7,
    )

    if not offers:
        await callback.message.answer("😔 Ничего не найдено.")
        await state.clear()
        return

    text = "🔁 Лучшие варианты:\n\n"
    for o in offers:
        out = o["outbound"]
        inn = o["inbound"]
        text += (
            f"✈️ {out['origin']} → {out['destination']} {out.get('departure_at','')[:10]}\n"
            f"✈️ {inn['origin']} → {inn['destination']} {inn.get('departure_at','')[:10]}\n"
            f"💰 {o['total_price']} RUB\n\n"
        )

    await callback.message.answer(text)
    await state.clear()
