from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

from ui.keyboards import main_menu

router = Router()

@router.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "✈️ Добро пожаловать!\n\n"
        "Я помогу найти самые дешёвые авиабилеты.\n"
        "Выбери действие ⬇️",
        reply_markup=main_menu()
    )
