# ui/states.py
from aiogram.fsm.state import StatesGroup, State

class SearchStates(StatesGroup):
    origin = State()
    destination = State()
    trip_type = State()        # one_way | round_trip
    passengers = State()       # int
    depart_date = State()
    return_date = State()
