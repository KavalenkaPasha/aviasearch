# services/travelpayouts.py
import aiohttp
import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Union, Optional

from config import TRAVELPAYOUTS_TOKEN

# Настраиваем отдельный логгер для API запросов
logger = logging.getLogger(__name__)

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

AIRLINE_NAMES = {
    "SU": "Аэрофлот", "DP": "Победа", "S7": "S7 Airlines", "U6": "Уральские авиалинии",
    "UT": "Utair", "WZ": "Red Wings", "IO": "IrAero", "A4": "Azimuth",
    "TK": "Turkish Airlines", "EK": "Emirates", "FZ": "Flydubai", "QR": "Qatar Airways",
    "B2": "Belavia", "HY": "Uzbekistan Airways", "KC": "Air Astana",
    "DV": "SCAT", "J2": "AZAL",
}

def get_airline_name(iata_code: str) -> str:
    return AIRLINE_NAMES.get(iata_code, iata_code)

def _to_date(d: Union[date, datetime, str]) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()

async def _fetch(
    session: aiohttp.ClientSession,
    origin: str,
    destination: str,
    d: Union[date, datetime, str],
    limit: int = 10,
) -> List[dict]:
    if isinstance(d, (str, datetime)):
        d = _to_date(d)

    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": d.strftime("%Y-%m-%d"),
        "currency": "rub",
        "limit": str(limit),
        "token": TRAVELPAYOUTS_TOKEN,
        "one_way": "true",
    }

    try:
        async with session.get(API_URL, params=params) as r:
            # Логируем полный URL (без токена для безопасности, либо с ним для полной проверки)
            logger.info(f"🔍 Запрос: {origin}->{destination} на {d} | URL: {r.url}")
            
            if r.status == 200:
                data = await r.json()
                # ВАЖНО: Логируем сколько записей реально пришло
                raw_data = data.get("data", [])
                logger.info(f"📥 Ответ API: получено рейсов: {len(raw_data)}")
                
                # Если нужно увидеть структуру первого рейса (для отладки парсинга):
                if raw_data:
                    logger.debug(f"📋 Пример данных первого рейса: {raw_data[0]}")
                
                return raw_data
            
            text = await r.text()
            logger.error(f"❌ Ошибка API {r.status}: {text}")
            return []
            
    except Exception as e:
        logger.exception(f"💥 Сетевая ошибка: {e}")
        return []

async def search_flights_for_dates(
    origin: str,
    destination: str,
    dates: List[Union[date, datetime, str]],
    limit_per_day: int = 10,
    session: Optional[aiohttp.ClientSession] = None
) -> List[dict]:
    if session:
        return await _execute_search(session, origin, destination, dates, limit_per_day)
    else:
        async with aiohttp.ClientSession() as local_session:
            return await _execute_search(local_session, origin, destination, dates, limit_per_day)

async def _execute_search(
    session: aiohttp.ClientSession,
    origin: str,
    destination: str,
    dates: List[Union[date, datetime, str]],
    limit_per_day: int
) -> List[dict]:
    # Используем asyncio.gather для параллельных запросов по всем датам (±7 дней)
    tasks = [
        _fetch(session, origin, destination, d, limit_per_day) 
        for d in dates
    ]
    responses = await asyncio.gather(*tasks)
    
    results = []
    for resp in responses:
        results.extend(resp)

    valid_results = [
        r for r in results
        if r.get("price") is not None and float(r["price"]) > 0
    ]

    valid_results.sort(key=lambda x: float(x.get("price", 1e12)))
    return valid_results

async def search_round_trip_fixed_stay(
    origin: str,
    destination: str,
    depart_date: Union[date, datetime, str],
    return_date: Union[date, datetime, str],
    *,
    days_flex: int = 7,
    passengers: int = 1,
    limit: int = 5,
    session: Optional[aiohttp.ClientSession] = None
) -> List[Dict]:
    """
    Ищет билеты туда-обратно с сохранением интервала (stay_days) в диапазоне ±days_flex от depart_date.
    """
    d_date = _to_date(depart_date)
    r_date = _to_date(return_date)
    stay_days = (r_date - d_date).days
    
    # Генерируем даты вылета: [Anchor-7 ... Anchor+7]
    depart_dates = [
        d_date + timedelta(days=i) 
        for i in range(-days_flex, days_flex + 1)
    ]
    # Фильтруем прошлое
    today = datetime.now().date()
    depart_dates = [d for d in depart_dates if d >= today]

    if not depart_dates:
        return []
    
    # Даты возврата жестко привязаны к дате вылета через stay_days
    # (если вылет сдвинулся на +1 день, возврат тоже сдвигается на +1 день)
    target_return_dates = [d + timedelta(days=stay_days) for d in depart_dates]
    
    # Нужно запросить API для всех дат вылета и всех целевых дат возврата
    # (API принимает конкретную дату, а не список)
    
    is_local = False
    if not session:
        session = aiohttp.ClientSession()
        is_local = True

    try:
        # Запускаем поиск "Туда"
        out_task = search_flights_for_dates(origin, destination, depart_dates, limit_per_day=5, session=session)
        # Запускаем поиск "Обратно" (для вычисленных дат)
        in_task = search_flights_for_dates(destination, origin, target_return_dates, limit_per_day=5, session=session)
        
        outbound_res, inbound_res = await asyncio.gather(out_task, in_task)
        
        # Группируем inbound по датам для быстрого поиска
        in_map = {}
        for item in inbound_res:
            d_str = item.get("departure_at", "")[:10]
            if d_str not in in_map:
                in_map[d_str] = []
            in_map[d_str].append(item)
            
        combinations = []
        
        for out in outbound_res:
            out_d_str = out.get("departure_at", "")[:10]
            out_date_obj = _to_date(out_d_str)
            
            # Вычисляем, когда должен быть возврат для ЭТОГО вылета
            required_return_date = out_date_obj + timedelta(days=stay_days)
            req_ret_str = required_return_date.strftime("%Y-%m-%d")
            
            # Ищем, есть ли билеты обратно именно на эту дату
            matching_inbound = in_map.get(req_ret_str, [])
            
            for inn in matching_inbound:
                # Цена API обычно за 1 пассажира. Считаем итог.
                p_out = float(out.get("price", 0))
                p_in = float(inn.get("price", 0))
                total = (p_out + p_in) * passengers
                
                combinations.append({
                    "outbound": out,
                    "inbound": inn,
                    "total_price": int(total)
                })
        
        combinations.sort(key=lambda x: x["total_price"])
        return combinations[:limit]
    finally:
        if is_local:
            await session.close()
async def _execute_round_trip(
    session: aiohttp.ClientSession,
    origin: str,
    destination: str,
    depart_dates: List[date],
    stay_days: int,
    passengers: int,
    limit: int
) -> List[Dict]:
    
    # Даты возврата строго привязаны к датам вылета (+ stay_days)
    return_dates = [d + timedelta(days=stay_days) for d in depart_dates]

    outbound_task = _execute_search(session, origin, destination, depart_dates, limit_per_day=5)
    inbound_task = _execute_search(session, destination, origin, return_dates, limit_per_day=5)
    
    outbound, inbound = await asyncio.gather(outbound_task, inbound_task)

    results = []
    inbound_map = {}
    for i in inbound:
        i_date = i.get("departure_at", "")[:10]
        if i_date not in inbound_map:
            inbound_map[i_date] = []
        inbound_map[i_date].append(i)

    for o in outbound:
        o_date_str = o.get("departure_at", "")[:10]
        o_date = _to_date(o_date_str)
        
        target_return_date = o_date + timedelta(days=stay_days)
        target_return_str = target_return_date.strftime("%Y-%m-%d")

        matching_inbound = inbound_map.get(target_return_str, [])
        
        for i in matching_inbound:
            try:
                total = (float(o["price"]) + float(i["price"])) * passengers
                results.append({
                    "outbound": o,
                    "inbound": i,
                    "total_price": int(total),
                })
            except Exception:
                continue

    results.sort(key=lambda x: x["total_price"])
    return results[:limit]