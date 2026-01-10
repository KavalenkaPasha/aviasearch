# services/scheduler.py
import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot
from database import get_all_subscriptions, set_last_notified, update_subscription_threshold
from services.travelpayouts import (
    search_round_trip_fixed_stay,
    search_flights_for_dates,
    get_airline_name
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
def safe_parse_date(value):
    """Парсер, устойчивый к разным форматам дат в БД."""
    if not value or str(value).strip() in ("0", "00--", "", "None", "null", "False"):
        return None
        
    if hasattr(value, "date"):
        return value.date()
        
    if isinstance(value, str):
        v = value.strip().split(" ")[0]
        # Если дата в формате YYYY-MM-DD
        if "-" in v:
            try:
                return datetime.strptime(v, "%Y-%m-%d").date()
            except: pass
        # Если дата в формате YYYYMMDD
        if len(v) == 8 and v.isdigit():
            try:
                return datetime.strptime(v, "%Y%m%d").date()
            except: pass
            
    return None
async def check_subscriptions_task(bot: Bot):
    """
    Главный цикл проверки подписок с расширенным логированием и защитой от ошибок.
    """
    logger.info("🤖 Планировщик запущен")
    
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                logger.info("⏳ --- НАЧАЛО ЦИКЛА ПРОВЕРКИ ---")
                
                subs = get_all_subscriptions()
                if not subs:
                    logger.info("Подписок в базе данных не обнаружено.")
                
                for i, sub in enumerate(subs, 1):
                    try:
                        sub_id = sub.get('id')
                        origin = sub.get('origin')
                        destination = sub.get('destination')
                        threshold = sub.get('threshold') or 0
                        passengers = sub.get('passengers') or 1
                        
                        depart_date = safe_parse_date(sub.get('depart_date'))
                        return_date = safe_parse_date(sub.get('return_date'))

                        # Лог начала обработки подписки
                        logger.info(f"🔎 Обработка подписки #{sub_id}: {origin} -> {destination}")
                        
                        # --- ИСПРАВЛЕНИЕ: Пропускаем подписку, если дата вылета невалидна ---
                        if not depart_date:
                            logger.warning(f"⚠️ Sub #{sub_id}: Некорректная дата вылета (None). Подписка пропущена.")
                            continue
                        # -------------------------------------------------------------------

                        logger.debug(f"Sub #{sub_id} params: depart_date={depart_date}, return_date={return_date}, passengers={passengers}, stored_threshold={threshold}, threshold_flag={sub.get('threshold_is_manual')}")
                        
                        # Формируем диапазон дат ±7 дней
                        search_dates = [depart_date + timedelta(days=shift) for shift in range(-7, 8)]
                        
                        found_price = 0
                        best_offer_meta = {}

                        if return_date:
                            # ПОИСК ТУДА-ОБРАТНО
                            stay_days = (return_date - depart_date).days
                            offers = await search_round_trip_fixed_stay(
                                origin=origin,
                                destination=destination,
                                depart_date=depart_date,
                                return_date=return_date,
                                passengers=passengers,
                                days_flex=7,
                                limit=5,
                                session=session
                            )
                            logger.info(f"📊 Sub #{sub_id}: Получено {len(offers)} комбинаций 'туда-обратно' от API")

                            if offers:
                                offers.sort(key=lambda x: x['total_price'])
                                found_price = offers[0]['total_price']
                                best_offer_meta = offers[0]

                                # Debug preview
                                logger.debug(f"Sub #{sub_id} best_offer_meta preview: {str(best_offer_meta)[:800]}")
                                logger.info(f"Sub #{sub_id}: Found round-trip price: {found_price}")

                        # ПОИСК В ОДНУ СТОРОНУ
                        else:
                            results = await search_flights_for_dates(
                                origin=origin,
                                destination=destination,
                                dates=search_dates,
                                limit_per_day=5,
                                session=session
                            )
                            logger.info(f"📊 Sub #{sub_id}: Получено {len(results)} билетов в одну сторону от API")

                            if results:
                                results.sort(key=lambda x: float(x.get('price', 999999)))
                                raw_price = float(results[0].get('price', 0))
                                found_price = int(raw_price * passengers)
                                best_offer_meta = results[0]

                                # Debug preview
                                logger.debug(f"Sub #{sub_id} best_offer_meta preview: {str(best_offer_meta)[:800]}")
                                logger.info(f"Sub #{sub_id}: Found one-way price: {found_price} (raw: {raw_price})")

                        # ЛОГ: Проверка найденной цены
                        if found_price > 0:
                            logger.info(f"💰 Sub #{sub_id}: Лучшая цена {found_price} RUB (Ваш порог: {threshold})")
                            
                            last_notified = sub.get('last_notified_price')
                            
                            # Проверка условий отправки уведомления
                            if found_price <= threshold and found_price != last_notified:
                                logger.info(f"🎯 Условие выполнено! Отправка уведомления пользователю {sub['user_id']}")
                                
                                airline_name = get_airline_name(best_offer_meta.get('airline', ''))
                                
                                if return_date:
                                    d_str = best_offer_meta.get('outbound', {}).get('departure_at', '')[:10]
                                    r_str = best_offer_meta.get('inbound', {}).get('departure_at', '')[:10]
                                    dates_str = f"{d_str} ⇄ {r_str}"
                                else:
                                    dates_str = f"{best_offer_meta.get('departure_at', '')[:10]}"

                                text = (
                                    f"🔔 <b>Цена упала! (±7 дней)</b>\n"
                                    f"✈️ {origin} → {destination}\n"
                                    f"📅 {dates_str}\n"
                                    f"🏢 {airline_name}\n\n"
                                    f"💰 <b>{found_price} RUB</b>\n"
                                    f"🎯 Цель: {int(threshold)} RUB"
                                )
                                
                                try:
                                    await bot.send_message(chat_id=sub['user_id'], text=text, parse_mode="HTML")
                                    # Обновляем last_notified
                                    set_last_notified(sub_id, found_price)
                                    logger.info(f"📩 Сообщение отправлено в Telegram")

                                    # Если порог был динамическим, обновляем его
                                    try:
                                        if sub.get("threshold_is_manual") in (0, "0", False):
                                            update_subscription_threshold(sub_id, found_price, threshold_is_manual=0)
                                            logger.info(f"🔁 Sub #{sub_id}: Порог обновлён (динамический) -> {found_price}")
                                    except Exception as e:
                                        logger.exception(f"Ошибка обновления порога для подписки {sub_id}: {e}")

                                except Exception as e:
                                    logger.error(f"Ошибка отправки сообщения: {e}")
                            else:
                                if found_price > threshold:
                                    logger.info(f"⏭️ Цена {found_price} выше порога {threshold}, уведомление не нужно.")
                                elif found_price == last_notified:
                                    logger.info(f"⏭️ Цена {found_price} уже была сообщена ранее.")
                        else:
                            logger.info(f"🔸 Sub #{sub_id}: API не вернул ни одного билета на эти даты.")

                    except Exception as e:
                        logger.exception(f"Критическая ошибка при обработке подписки {sub.get('id')}: {e}")
                    
                    # Маленькая пауза между подписками для стабильности
                    await asyncio.sleep(1.5)

            logger.info("✅ --- ЦИКЛ ЗАВЕРШЕН. Сон 10 минут ---")
            await asyncio.sleep(600)

        except Exception as e:
            logger.exception("Ошибка в основном цикле планировщика. Перезапуск через 60с...")
            await asyncio.sleep(60)