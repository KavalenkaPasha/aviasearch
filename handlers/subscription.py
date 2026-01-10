# handlers/subscription.py
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext

from database import (
    add_subscription,
    get_user_subscriptions,
    delete_subscription,
    update_subscription_threshold,
)
from ui.keyboards import subscriptions_keyboard, threshold_options_keyboard, start_inline_menu
from ui.states import SubscriptionStates
from services.travelpayouts import (
    search_round_trip_fixed_stay,
    search_flights_for_dates,
)

# Initialize logger
logger = logging.getLogger(__name__)

router = Router()

# --- Helpers ---

def uncompact_date(date_str: str) -> str:
    """Обеспечивает формат YYYY-MM-DD или возвращает None."""
    if not date_str or str(date_str).strip() in ("0", "None", "", "False"):
        return None
    
    # Очистка от времени (если есть) и пробелов
    s = str(date_str).strip().split(" ")[0]
    
    if "-" in s:
        return s
        
    if len(s) >= 8 and s[:8].isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        
    return s if s else None

def safe_parse_date(value):
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if v in ("0", "00--", "", "None"):
            return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None

def normalize_return_date_for_storage(value):
    """
    Robust normalization:
    - If string contains YYYY-MM-DD anywhere -> return that match.
    - Else if string contains an 8-digit sequence (YYYYMMDD) -> format to YYYY-MM-DD.
    - Else try strict parse of leading YYYY-MM-DD.
    """
    if value is None:
        return None

    s = str(value).strip()
    if s in ("0", "00--", "", "None"):
        return None

    # lazy local import to avoid moving module-level imports
    import re
    from datetime import datetime

    # 1) поиск ISO-формата YYYY-MM-DD внутри строки
    m = re.search(r'(\d{4}-\d{2}-\d{2})', s)
    if m:
        return m.group(1)

    # 2) поиск первой группы из 8 цифр (YYYYMMDD)
    m2 = re.search(r'(\d{8})', s)
    if m2:
        v = m2.group(1)
        return f"{v[:4]}-{v[4:6]}-{v[6:8]}"

    # 3) попытка строгого парсинга из начала строки (на всякий случай)
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date().strftime("%Y-%m-%d")
    except Exception:
        return None

# --- Handlers ---

@router.callback_query(F.data.startswith("sub:"))
async def subscribe_handler(callback: CallbackQuery, state: FSMContext):
    try:
        raw = callback.data
        logger.debug(f"subscribe_handler raw cb: {raw}")

        parts = raw.split(":")
        # Expected: sub:<price>:<origin>:<dest>:<departYYYYMMDD>:<retYYYYMMDD or 0>:<passengers>
        price = int(float(parts[1])) if len(parts) > 1 and parts[1] else 0.0
        origin = parts[2] if len(parts) > 2 else None
        destination = parts[3] if len(parts) > 3 else None

        # safe parse depart
        d_raw = parts[4] if len(parts) > 4 else "0"
        depart_date = None
        if d_raw and d_raw != "0":
            if len(d_raw) == 8 and d_raw.isdigit():
                depart_date = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
            else:
                depart_date = d_raw

        # safe parse return
        r_raw = parts[5] if len(parts) > 5 else "0"
        return_date = None
        if r_raw and r_raw not in ("0", "", "None"):
            if len(r_raw) == 8 and r_raw.isdigit():
                return_date = f"{r_raw[:4]}-{r_raw[4:6]}-{r_raw[6:8]}"
            else:
                return_date = r_raw

        # passengers
        try:
            parsed_passengers = int(parts[6]) if len(parts) > 6 else None
            if parsed_passengers is not None and parsed_passengers < 1:
                parsed_passengers = 1
        except Exception:
            parsed_passengers = None

        logger.debug(f"subscribe_handler parsed: origin={origin} dest={destination} depart={depart_date} return={return_date} passengers(parsed)={parsed_passengers} price={price}")

        # --- MERGE WITH EXISTING STATE: do NOT overwrite correct data in state ---
        existing_state = await state.get_data()
        existing_sub = existing_state.get("sub_params", {}) if existing_state else {}

        # If state already has full data for this route, prefer it.
        if (existing_sub
            and existing_sub.get("origin") == origin
            and existing_sub.get("destination") == destination
            and existing_sub.get("depart")  # depart present in state
        ):
            merged = existing_sub.copy()
            # Only fill missing fields from parsed callback
            if not merged.get("return") and return_date:
                merged["return"] = return_date
            if not merged.get("passengers") and parsed_passengers is not None:
                merged["passengers"] = parsed_passengers
            # if parsed_passengers present but existing has passengers, keep existing (trusted)
            logger.info("subscribe_handler: merged parsed callback with existing state.sub_params")
        else:
            # No reliable existing state -> use parsed values, but ensure defaults are sane
            merged = {
                "origin": origin,
                "destination": destination,
                "depart": depart_date,
                "return": return_date,
                "passengers": parsed_passengers if parsed_passengers is not None else 1
            }
            logger.info("subscribe_handler: using parsed values from callback to set state.sub_params")

        # Final normalization: ensure passengers is int
        try:
            merged["passengers"] = int(merged.get("passengers", 1))
            if merged["passengers"] < 1:
                merged["passengers"] = 1
        except Exception:
            merged["passengers"] = 1

        await state.update_data(sub_params=merged)
        await state.update_data(edit_sub_id=None)

        kb = threshold_options_keyboard(
            price,
            origin,
            destination,
            depart_date,
            return_date or "0",
            merged.get("passengers", 1)
        )

        await callback.answer()
        await callback.message.answer("Выберите целевую цену для подписки:", reply_markup=kb)
    except Exception as e:
        await callback.answer("Ошибка при подготовке подписки", show_alert=True)
        logger.exception("subscribe_handler error: %s", e)

@router.callback_query(F.data.startswith("set_threshold_manual:"))
async def cb_set_threshold_manual(call: CallbackQuery, state: FSMContext):
    try:
        parts = call.data.split(":")
        if len(parts) == 2:
            # формат редактирования: set_threshold_manual:<sub_id>
            sub_id = int(parts[1])
            subs = get_user_subscriptions(call.from_user.id)
            sub = next((s for s in subs if s["id"] == sub_id), None)
            if not sub:
                await call.answer("Подписка не найдена", show_alert=True)
                return

            await state.update_data(
                edit_sub_id=sub_id,
                sub_params={
                    "origin": sub["origin"],
                    "destination": sub["destination"],
                    "depart": uncompact_date(sub["depart_date"]),
                    "return": normalize_return_date_for_storage(sub["return_date"]),
                    "passengers": sub["passengers"]
                }
            )
            await state.set_state(SubscriptionStates.waiting_for_manual_threshold)
            await call.answer()
            await call.message.answer("Введите целевую цену в рублях (только число), например: 19999")
            return

        # 1. ПРИОРИТЕТ: Пробуем взять полные данные из существующего состояния
        # Это решает проблему потери кол-ва пассажиров и дат
        state_data = await state.get_data()
        current_sub_params = state_data.get("sub_params", {})
        
        # Проверяем, совпадают ли данные в стейте с тем, на что кликнули (защита от старых кнопок)
        if (current_sub_params 
            and current_sub_params.get("origin")
            and current_sub_params.get("destination")
            and "passengers" in current_sub_params):
            logger.info("cb_set_threshold_manual: Используем данные из кэша State")
        else:
            logger.error("cb_set_threshold_manual: Отсутствуют данные в State — прерываем операцию")
            await call.answer("Ошибка состояния. Повторите поиск заново.", show_alert=True)
            return
        
        await state.set_state(SubscriptionStates.waiting_for_manual_threshold)
        await call.answer()
        await call.message.answer("Введите целевую цену в рублях (только число), например: 19999")
        
    except Exception as e:
        logger.exception("cb_set_threshold_manual error: %s", e)
        await call.answer("Ошибка данных", show_alert=True)

@router.callback_query(F.data.startswith("set_threshold_use:"))
async def cb_set_threshold_use(call: CallbackQuery, state: FSMContext):
    try:
        raw = call.data
        logger.debug(f"cb_set_threshold_use raw callback: {raw}")

        parts = raw.split(":")
        if len(parts) == 2:
            sub_id = int(parts[1])
            st = await state.get_data()
            current_price = st.get("current_price")

            if not current_price:
                await call.answer("Текущая цена недоступна", show_alert=True)
                return

            update_subscription_threshold(sub_id, int(round(float(current_price))), threshold_is_manual=0)
            await call.answer()
            await call.message.edit_text("✅ Целевая цена обновлена (используется текущая)", reply_markup=start_inline_menu())
            await state.clear()
            return

        price = int(float(parts[1]))

        st = await state.get_data()
        edit_id = st.get("edit_sub_id")
        sub_params = st.get("sub_params")

        if edit_id:
            logger.info(f"cb_set_threshold_use: updating sub {edit_id} -> price={price}")
            update_subscription_threshold(edit_id, int(round(float(price))), threshold_is_manual=0)
            await call.answer()
            await call.message.edit_text(f"✅ Целевая цена подписки обновлена: {int(price)} RUB", reply_markup=start_inline_menu())
            await state.clear()
            return

        if sub_params:
            origin = sub_params["origin"]
            destination = sub_params["destination"]
            depart = sub_params["depart"]
            ret = sub_params["return"]
            passengers = int(sub_params.get("passengers", 1))
        else:
            origin = parts[2]
            destination = parts[3]
            depart_raw = parts[4]
            ret_raw = parts[5]
            passengers = int(parts[6]) if len(parts) > 6 else 1
            
            depart = f"{depart_raw[:4]}-{depart_raw[4:6]}-{depart_raw[6:8]}" if depart_raw and depart_raw != "0" else None
            ret = f"{ret_raw[:4]}-{ret_raw[4:6]}-{ret_raw[6:8]}" if ret_raw and ret_raw != "0" else None

        # Check strict requirement for depart date
        if not depart or depart == "0":
             await call.answer("Ошибка: не указана дата вылета", show_alert=True)
             return

        clean_depart = uncompact_date(depart)
        clean_return = normalize_return_date_for_storage(ret)

        add_subscription(
            user_id=call.from_user.id,
            origin=origin,
            destination=destination,
            depart_date=clean_depart,
            return_date=clean_return,
            passengers=passengers,
            threshold=price,
            threshold_is_manual=0
        )
        await call.answer()

        ui_depart = uncompact_date(depart)
        ui_ret = normalize_return_date_for_storage(ret)

        route_text = f"✈️ <b>Подписка оформлена!</b>\n\nRoute: {origin} → {destination}"
        if ui_ret:
            route_text += f"\nDates: {ui_depart} — {ui_ret}"
        else:
            route_text += f"\nDate: {ui_depart}"
        route_text += f"\n💰 Target: <b>{int(price)} RUB</b> (динамический)"

        await call.message.edit_text(route_text, parse_mode="HTML", reply_markup=start_inline_menu())
        await state.clear()
    except Exception as e:
        logger.exception("cb_set_threshold_use error: %s", e)
        await call.answer("Ошибка при сохранении подписки", show_alert=True)

@router.message(SubscriptionStates.waiting_for_manual_threshold)
async def process_manual_threshold(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        sub_params = data.get("sub_params")
        if not sub_params:
            await message.answer("Ошибка состояния. Начните поиск заново.")
            return

        price_text = message.text.strip().replace(" ", "")
        if not price_text.isdigit():
            await message.answer("Пожалуйста, введите число (например, 15000).")
            return
        
        threshold = int(round(float(price_text)))
        user_id = message.from_user.id
        
        # --- FIX: Очищаем даты перед использованием, на случай если в State попал мусор ---
        depart_raw = sub_params.get("depart")
        return_raw = sub_params.get("return")
        
        depart = uncompact_date(depart_raw)
        ret = uncompact_date(return_raw)
        # ---------------------------------------------------------------------------------

        if not depart:
            logger.warning(f"process_manual_threshold: invalid depart: raw={depart_raw} parsed={depart} user={user_id}")
            await message.answer("Ошибка даты вылета. Попробуйте снова.")
            return

# Финальная очистка перед записью в БД
        clean_depart = uncompact_date(sub_params.get("depart"))
        raw_return = sub_params.get("return")
        clean_return = normalize_return_date_for_storage(raw_return)
        
        # Гарантируем, что пассажиры — это целое число
        try:
            clean_passengers = int(sub_params.get("passengers", 1))
        except (ValueError, TypeError):
            clean_passengers = 1

        add_subscription(
            user_id=user_id,
            origin=sub_params["origin"],
            destination=sub_params["destination"],
            depart_date=clean_depart,
            return_date=clean_return, # Теперь тут либо 'YYYY-MM-DD', либо None
            passengers=clean_passengers,
            threshold=threshold,
            threshold_is_manual=1
        )
        
        await state.clear()
        await message.answer(
            f"✅ Подписка создана! Я сообщу, когда цена упадет ниже {threshold} руб.",
            reply_markup=start_inline_menu()
        )
        
    except Exception as e:
        logger.exception("process_manual_threshold error: %s", e)
        await message.answer("Произошла ошибка при сохранении подписки.")

@router.message(F.text.contains("Мои подписки"))
@router.callback_query(F.data == "my_subs")
async def list_subscriptions(event):
    # Determine if it's a message or callback
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = event.from_user.id
        await event.answer()
    else:
        message = event
        user_id = event.from_user.id

    try:
        subs = get_user_subscriptions(user_id)
    except Exception as e:
        logger.error(f"Error getting subscriptions for {user_id}: {e}")
        subs = []

    if not subs:
        text = "📂 У вас нет активных подписок."
        if isinstance(event, CallbackQuery):
            await message.edit_text(text, reply_markup=start_inline_menu())
        else:
            await message.answer(text, reply_markup=start_inline_menu())
        return

    lines = ["⭐ <b>Ваши подписки (нажмите ✏️ для редактирования):</b>\n"]
    kb_buttons = []
    
    for s in subs:
        sub_id = s["id"]
        origin = s["origin"]
        dest = s["destination"]
        dep = s["depart_date"]
        ret = s["return_date"] or "—"
        pax = s.get("passengers", 1)
        threshold = s.get("threshold") or "—"
        flag = "ручной" if s.get("threshold_is_manual") in (1, "1", True) else "динамический"
        last_found = s.get("last_notified_price") or "—"

        lines.append(
            f"ID:{sub_id} — {origin} → {dest}\n"
            f"Даты: {dep} — {ret}\n"
            f"Пассажиров: {pax}\n"
            f"Триггер: {threshold} ({flag})\n"
            f"Последняя найденная цена: {last_found}\n"
            "—\n"
        )

        # InlineKeyboardButton is imported at the top, so this should work fine
        kb_buttons.append([
            InlineKeyboardButton(text=f"✏️ Редактировать {sub_id}", callback_data=f"edit_sub:{sub_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"del_sub:{sub_id}")
        ])

    kb_buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="go_home")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_buttons)

    full_text = "\n".join(lines)
    
    if isinstance(event, CallbackQuery):
        await message.edit_text(full_text, parse_mode="HTML", reply_markup=kb)
    else:
        await message.answer(full_text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("edit_sub:"))
async def edit_sub_handler(call: CallbackQuery, state: FSMContext):
    try:
        sub_id_str = call.data.split(":")[1]
        sub_id = int(sub_id_str)
        subs = get_user_subscriptions(call.from_user.id)
        sub = next((s for s in subs if s["id"] == sub_id), None)
        
        if not sub:
            await call.answer("Подписка не найдена", show_alert=True)
            return

        await state.update_data(edit_sub_id=sub_id, sub_params={
            "origin": sub["origin"],
            "destination": sub["destination"],
            "depart": uncompact_date(sub["depart_date"]),
            "return": normalize_return_date_for_storage(sub["return_date"]),
            "passengers": sub["passengers"]
        })

        # Calculate current price for reference
        current_price = 0
        try:
            d_obj = safe_parse_date(sub.get("depart_date"))
            r_obj = safe_parse_date(sub.get("return_date"))
            
            if r_obj:
                offers = await search_round_trip_fixed_stay(
                    origin=sub["origin"],
                    destination=sub["destination"],
                    depart_date=d_obj,
                    return_date=r_obj,
                    passengers=sub["passengers"],
                    days_flex=1
                )
                if offers:
                    current_price = min(o["total_price"] for o in offers if o.get("total_price"))
            elif d_obj:
                results = await search_flights_for_dates(
                    origin=sub["origin"],
                    destination=sub["destination"],
                    dates=[d_obj],
                    limit_per_day=3
                )
                if results:
                    current_price = int(float(results[0].get("price", 0)) * sub["passengers"])
        except Exception:
            current_price = 0

        if not current_price:
            if sub.get("last_notified_price"):
                current_price = int(sub["last_notified_price"])
            elif sub.get("threshold"):
                current_price = int(sub["threshold"])
                
        await state.update_data(current_price=current_price)
        
        threshold = sub.get("threshold")
        threshold_flag = sub.get("threshold_is_manual")
        last_notified = sub.get("last_notified_price")

        flag_text = "ручной" if threshold_flag else "динамический"
        threshold_str = f"{threshold} RUB" if threshold else "—"
        last_notified_str = f"{int(last_notified)} RUB" if last_notified else "—"

        edit_text = (
            f"Редактирование подписки:\n"
            f"{sub['origin']} → {sub['destination']}\n"
            f"Даты: {sub['depart_date']}" + (f" — {sub['return_date']}" if sub['return_date'] else "") + "\n"
            f"Пассажиров: {sub['passengers']}\n\n"
            f"Установленный триггер: {threshold_str} ({flag_text})\n"
            f"Последняя найденная цена: {last_notified_str}\n\n"
            "Введите новую цену (или нажмите 'Использовать текущую цену'):"
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"Использовать текущую цену: {int(current_price)} RUB",
                callback_data=f"set_threshold_use:{sub_id}"
            )],
            [InlineKeyboardButton(
                text="Ввести цену вручную",
                callback_data=f"set_threshold_manual:{sub_id}"
            )],
            [InlineKeyboardButton(text="Отмена", callback_data="subscribe_cancel")]
        ])

        await call.message.edit_text(edit_text, parse_mode="HTML", reply_markup=kb)
        await call.answer()
    except Exception as e:
        await call.answer("Ошибка редактирования", show_alert=True)
        logger.exception("edit_sub_handler error: %s", e)

@router.callback_query(F.data.startswith("del_sub:"))
async def del_sub_handler(callback: CallbackQuery):
    try:
        sub_id = int(callback.data.split(":")[1])
        delete_subscription(sub_id)
        await callback.answer("Подписка удалена")
        
        subs = get_user_subscriptions(callback.from_user.id)
        if not subs:
            await callback.message.edit_text("Список подписок пуст.", reply_markup=start_inline_menu())
        else:
            # Re-render list
            # Note: We need to manually rebuild the text/keyboard as list_subscriptions does.
            # To simplify, we can call list_subscriptions logic or redirect.
            # Here we just refresh the view if possible.
            await list_subscriptions(callback) 
            
    except Exception as e:
        await callback.answer("Ошибка удаления", show_alert=True)
        logger.exception("del_sub_handler error: %s", e)

@router.callback_query(F.data == "subscribe_cancel")
async def subscribe_cancel_handler(callback: CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.edit_text("Операция отменена.", reply_markup=start_inline_menu())
        except Exception:
            await callback.message.answer("Операция отменена.", reply_markup=start_inline_menu())
        await callback.answer()
    except Exception as e:
        logger.exception("subscribe_cancel_handler error: %s", e)
        await callback.answer("Ошибка при отмене", show_alert=True)

@router.callback_query(F.data == "close_subs_list")
async def close_subs_list(callback: CallbackQuery):
    try:
        await callback.message.delete()
        await callback.message.answer("Главное меню:", reply_markup=start_inline_menu())
    except Exception:
        pass