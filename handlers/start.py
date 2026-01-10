# handlers/start.py
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ui.keyboards import start_inline_menu

router = Router()

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "✈️ <b>Добро пожаловать!</b>\n\n"
        "Я помогу найти самые дешёвые авиабилеты.\n"
        "Выберите действие ниже:",
        reply_markup=start_inline_menu(),
        parse_mode="HTML"
    )

@router.callback_query(lambda c: c.data == "go_home")
async def go_home_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "🏠 Главное меню:",
        reply_markup=start_inline_menu()
    )
    await callback.answer()