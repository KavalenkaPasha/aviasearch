# services/scheduler.py
import asyncio
import logging
import re
from datetime import datetime
from aiogram import Bot
from database import get_all_subscriptions
from services.travelpayouts import (
    search_round_trip_fixed_stay, 
    search_flights_for_dates,
    get_airline_name # <--- Импортируем
)

logger = logging.getLogger(__name__)

def clean_date_string(date_val):
    if not date_val or str(date_val) == "0":
        return None
    date_str = str(date_val).strip()[:10]
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return date_str
    return None

async def check_subscriptions_task(bot: Bot):
    while True:
        logger.info("⏳ Starting subscription check...")
        try:
            subs = get_all_subscriptions()
            if not subs:
                logger.info("No subscriptions found.")
            
            for sub in subs:
                try:
                    dep_str = clean_date_string(sub.get('depart_date'))
                    ret_str = clean_date_string(sub.get('return_date')) # None если one-way

                    if not dep_str:
                        continue

                    passengers = sub['passengers']
                    offers = []
                    
                    # === ЛОГИКА ТУДА-ОБРАТНО ===
                    if ret_str:
                        offers = await search_round_trip_fixed_stay(
                            origin=sub['origin'],
                            destination=sub['destination'],
                            depart_date=dep_str,
                            return_date=ret_str,
                            passengers=passengers,
                            days_flex=2
                        )
                        # Форматируем данные для уведомления (если нашли)
                        if offers:
                            best = offers[0]
                            # Берем имя авиакомпании из вылета "туда"
                            airline_code = best['outbound'].get('airline', '')
                            offers = [{
                                "total_price": best['total_price'],
                                "airline_name": get_airline_name(airline_code),
                                "is_round": True
                            }]
                            
                    # === ЛОГИКА В ОДНУ СТОРОНУ ===
                    else:
                        d_obj = datetime.strptime(dep_str, "%Y-%m-%d").date()
                        results = await search_flights_for_dates(
                            origin=sub['origin'],
                            destination=sub['destination'],
                            dates=[d_obj],
                            limit_per_day=3
                        )
                        if results:
                            best = results[0]
                            # Проверка на корректную цену
                            raw_price = float(best.get('price', 0))
                            if raw_price > 0:
                                total = raw_price * passengers
                                offers = [{
                                    "total_price": int(total),
                                    "airline_name": get_airline_name(best.get('airline', '')),
                                    "is_round": False
                                }]

                    # === ОТПРАВКА УВЕДОМЛЕНИЯ ===
                    if offers:
                        best_offer = offers[0]
                        price = best_offer['total_price']
                        
                        # Дополнительная защита от 0 цены
                        if price <= 0:
                            logger.warning(f"Skipping sub {sub['id']} because price is 0")
                            continue

                        airline_name = best_offer['airline_name']
                        
                        route_info = f"📅 {dep_str}"
                        if best_offer['is_round']:
                            route_info += f" — {ret_str}"
                        else:
                            route_info += " (В одну сторону)"
                        
                        text = (
                            f"🔔 <b>Билет найден!</b>\n"
                            f"✈️ {sub['origin']} → {sub['destination']}\n"
                            f"{route_info}\n"
                            f"🏢 <b>{airline_name}</b>\n"
                            f"💰 <b>{price} RUB</b>"
                        )
                        await bot.send_message(chat_id=sub['user_id'], text=text, parse_mode="HTML")
                        logger.info(f"Notification sent to {sub['user_id']} Price: {price}")
                    
                    await asyncio.sleep(1) 

                except Exception as e:
                    logger.error(f"Error processing sub {sub.get('id')}: {e}")

        except Exception as e:
            logger.exception("Critical error in scheduler")

        logger.info("✅ Check finished. Sleeping for 1 hour.")
        await asyncio.sleep(20)