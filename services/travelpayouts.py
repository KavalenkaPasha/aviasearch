# services/travelpayouts.py
import aiohttp
from datetime import date, datetime, timedelta
from typing import List, Dict, Union

from config import TRAVELPAYOUTS_TOKEN

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"


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
    d: date,
    limit: int = 10,
) -> List[dict]:
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": d.strftime("%Y-%m-%d"),
        "currency": "rub",
        "limit": str(limit),
        "token": TRAVELPAYOUTS_TOKEN,
        "one_way": "true",
    }

    async with session.get(API_URL, params=params) as r:
        if r.status != 200:
            return []
        data = await r.json()
        return data.get("data", [])


async def search_flights_for_dates(
    origin: str,
    destination: str,
    dates: List[date],
    limit_per_day: int = 10,
) -> List[dict]:
    results = []
    async with aiohttp.ClientSession() as session:
        for d in dates:
            res = await _fetch(session, origin, destination, d, limit_per_day)
            results.extend(res)

    results.sort(key=lambda x: float(x.get("price", 1e12)))
    return results


async def search_round_trip_fixed_stay(
    origin: str,
    destination: str,
    depart_date: Union[date, datetime, str],
    return_date: Union[date, datetime, str],
    *,
    days_flex: int = 7,
    passengers: int = 1,
    limit: int = 5,
) -> List[Dict]:
    """
    🔒 ФИКСИРОВАННАЯ ДЛИТЕЛЬНОСТЬ ПОЕЗДКИ
    """
    depart_date = _to_date(depart_date)
    return_date = _to_date(return_date)

    stay_days = (return_date - depart_date).days
    if stay_days <= 0:
        return []

    # генерируем ТОЛЬКО парные даты
    depart_dates = [
        depart_date + timedelta(days=shift)
        for shift in range(-days_flex, days_flex + 1)
    ]

    return_dates = [
        d + timedelta(days=stay_days)
        for d in depart_dates
    ]

    outbound = await search_flights_for_dates(
        origin, destination, depart_dates
    )
    inbound = await search_flights_for_dates(
        destination, origin, return_dates
    )

    results = []

    for o in outbound:
        o_date = o.get("departure_at", "")[:10]
        for i in inbound:
            i_date = i.get("departure_at", "")[:10]
            try:
                if (
                    _to_date(i_date)
                    - _to_date(o_date)
                ).days == stay_days:
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
