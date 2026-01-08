# database.py
import sqlite3
from datetime import datetime

DB_NAME = "subscriptions.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                depart_date TEXT NOT NULL,
                return_date TEXT NOT NULL,
                passengers INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def get_subscriptions_count():
    """Возвращает количество активных подписок."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM subscriptions")
        return cursor.fetchone()[0]

def add_subscription(user_id, origin, destination, depart_date, return_date, passengers):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subscriptions (user_id, origin, destination, depart_date, return_date, passengers)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, origin, destination, str(depart_date), str(return_date), passengers))
        conn.commit()

def get_user_subscriptions(user_id):
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_subscriptions():
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions")
        return [dict(row) for row in cursor.fetchall()]

def delete_subscription(sub_id):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        conn.commit()