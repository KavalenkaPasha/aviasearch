# ui/states.py (обновлённый)
from aiogram.fsm.state import StatesGroup, State

class SearchStates(StatesGroup):
    origin = State()
    destination = State()
    trip_type = State()        # one_way | round_trip
    passengers = State()       # int
    depart_date = State()
    return_date = State()

class SubscriptionStates(StatesGroup):
    waiting_for_manual_threshold = State()  # ожидание ручного ввода цены
    waiting_for_edit_threshold = State()    # при редактировании существующей подписки
