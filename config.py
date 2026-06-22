import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Доступ к админ-панели только у этих Telegram ID (зашито в коде)
ADMIN_IDS: set[int] = {610269479}

ADMIN_ID = next(iter(ADMIN_IDS)) if ADMIN_IDS else 0

SALON_NAME = os.getenv("SALON_NAME", "Студия депиляции")
SALON_ADDRESS = os.getenv("SALON_ADDRESS", "г. Москва, ул. Примерная, д. 1")
SALON_PHONE = os.getenv("SALON_PHONE", "+7 (999) 123-45-67")
SALON_HOURS = os.getenv("SALON_HOURS", "Пн–Сб 10:00–20:00, Вс — выходной")


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
