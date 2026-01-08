# config.py
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TRAVELPAYOUTS_TOKEN = os.getenv("TRAVELPAYOUTS_TOKEN")
# Добавляем ID администратора для уведомлений
ADMIN_ID = os.getenv("ADMIN_ID") 

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not TRAVELPAYOUTS_TOKEN:
    raise RuntimeError("TRAVELPAYOUTS_TOKEN is not set")