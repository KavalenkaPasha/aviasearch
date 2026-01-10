# database.py
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

DB_NAME = "subscriptions.db"

def _conn():
    return sqlite3.connect(DB_NAME)

def init_db() -> None:
    """
    Инициализация БД: создаёт таблицу subscriptions при необходимости
    и добавляет недостающие колонки безопасно.
    """
    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                depart_date TEXT NOT NULL,
                return_date TEXT,
                passengers INTEGER NOT NULL,
                threshold REAL DEFAULT NULL,
                threshold_is_manual INTEGER DEFAULT 1,     -- 1 = manual, 0 = dynamic (use current)
                last_notified_price REAL DEFAULT NULL,
                last_notified_at TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Проверим колонки и добавим при необходимости
        cursor.execute("PRAGMA table_info(subscriptions)")
        cols = [row[1] for row in cursor.fetchall()]

        if "return_date" not in cols:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN return_date TEXT")
        if "threshold" not in cols:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN threshold REAL DEFAULT NULL")
        if "threshold_is_manual" not in cols:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN threshold_is_manual INTEGER DEFAULT 1")
        if "last_notified_price" not in cols:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN last_notified_price REAL DEFAULT NULL")
        if "last_notified_at" not in cols:
            cursor.execute("ALTER TABLE subscriptions ADD COLUMN last_notified_at TIMESTAMP DEFAULT NULL")
        conn.commit()

def add_subscription(
    user_id: int,
    origin: str,
    destination: str,
    depart_date: str,
    return_date: str | None,
    passengers: int,
    threshold: float | None = None,
    threshold_is_manual: int = 1
) -> int:
    # --- input sanitization (last defense) ---
    try:
        passengers = int(passengers)
        if passengers < 1:
            passengers = 1
    except Exception:
        passengers = 1

    if not depart_date:
        raise ValueError("depart_date must not be empty")

    depart_to_store = str(depart_date).split(" ")[0]
    if return_date is None:
        return_to_store = None
    else:
        s = str(return_date).strip()
        return_to_store = None if s in ("0", "00", "", "None") else s.split(" ")[0]

    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions (
                user_id, origin, destination,
                depart_date, return_date,
                passengers, threshold, threshold_is_manual
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            origin,
            destination,
            depart_to_store,
            return_to_store,
            passengers,
            threshold,
            int(bool(threshold_is_manual))
        ))
        conn.commit()
        return cursor.lastrowid

def update_subscription_threshold(sub_id: int, threshold: float, threshold_is_manual: Optional[int] = None) -> None:
    threshold = int(threshold)
    with _conn() as conn:
        cursor = conn.cursor()
        if threshold_is_manual is None:
            cursor.execute("UPDATE subscriptions SET threshold = ? WHERE id = ?", (threshold, sub_id))
        else:
            cursor.execute(
                "UPDATE subscriptions SET threshold = ?, threshold_is_manual = ? WHERE id = ?",
                (threshold, int(bool(threshold_is_manual)), sub_id)
            )
        conn.commit()

def set_last_notified(sub_id: int, price: float) -> None:
    price = int(price)
    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE subscriptions SET last_notified_price = ?, last_notified_at = ? WHERE id = ?",
            (price, datetime.utcnow().isoformat(), sub_id)
        )
        conn.commit()

def get_subscription_by_id(sub_id: int) -> Optional[Dict]:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_user_subscriptions(user_id: int) -> List[Dict]:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_all_subscriptions() -> List[Dict]:
    with _conn() as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def delete_subscription(sub_id: int) -> None:
    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        conn.commit()

def get_subscriptions_count() -> int:
    """
    Возвращает общее количество подписок в БД.
    Используется при старте бота для уведомления администратора.
    """
    with _conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM subscriptions")
        row = cursor.fetchone()
        return int(row[0]) if row else 0
