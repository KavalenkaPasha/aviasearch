# handlers/subscription.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from database import add_subscription, get_user_subscriptions, delete_subscription
from ui.keyboards import subscriptions_keyboard

router = Router()

@router.callback_query(F.data.startswith("sub:"))
async def subscribe_handler(callback: CallbackQuery):
    # Формат: sub:ORIG:DEST:YYYYMMDD:YYYYMMDD:P
    try:
        parts = callback.data.split(":")
        # parts[0] = 'sub'
        origin = parts[1]
        destination = parts[2]
        
        # Парсим дату вылета
        d_raw = parts[3]
        depart_date = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"

        # Парсим дату возврата
        r_raw = parts[4]
        if r_raw == "0":
            return_date = "0" # Сохраняем как "0" в БД
        else:
            return_date = f"{r_raw[:4]}-{r_raw[4:6]}-{r_raw[6:8]}"
                
        passengers = int(parts[5])
        
        add_subscription(
            user_id=callback.from_user.id,
            origin=origin,
            destination=destination,
            depart_date=depart_date,
            return_date=return_date,
            passengers=passengers
        )
        await callback.answer("✅ Подписка оформлена!")
        await callback.message.answer(f"🔔 Вы подписались на рейс {origin} → {destination}")
        
    except Exception as e:
        await callback.answer("Ошибка сохранения подписки", show_alert=True)
        print(f"Sub Error: {e}") # Для отладки в консоль

@router.message(F.text.contains("Мои подписки"))
async def list_subscriptions(message: Message):
    subs = get_user_subscriptions(message.from_user.id)
    if not subs:
        await message.answer("📂 У вас нет активных подписок.")
        return
    
    await message.answer(
        "Ваши подписки (нажмите, чтобы удалить):",
        reply_markup=subscriptions_keyboard(subs)
    )

@router.callback_query(F.data.startswith("del_sub:"))
async def delete_sub_handler(callback: CallbackQuery):
    try:
        sub_id = int(callback.data.split(":")[1])
        delete_subscription(sub_id)
        await callback.answer("Подписка удалена")
        
        # Обновляем список
        subs = get_user_subscriptions(callback.from_user.id)
        if not subs:
            # Если сообщений не осталось, меняем текст
            await callback.message.edit_text("Список подписок пуст.")
        else:
            # Иначе обновляем клавиатуру
            await callback.message.edit_reply_markup(reply_markup=subscriptions_keyboard(subs))
    except Exception as e:
        await callback.answer("Ошибка удаления", show_alert=True)