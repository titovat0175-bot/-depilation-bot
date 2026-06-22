import logging
from datetime import datetime, time as dt_time

from telegram.ext import ContextTypes

from config import SALON_NAME
from database.db import get_pending_reminders, mark_reminder_sent

logger = logging.getLogger(__name__)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now()
    for row in get_pending_reminders():
        booking_dt = datetime.combine(
            datetime.strptime(row["date"], "%Y-%m-%d").date(),
            dt_time.fromisoformat(row["start_time"]),
        )
        hours_left = (booking_dt - now).total_seconds() / 3600
        display_date = booking_dt.strftime("%d.%m.%Y")
        services = row["services"]

        if not row["reminder_day_sent"] and 23 <= hours_left <= 25:
            text = (
                f"\U0001f514 <b>Напоминание</b>\n\n"
                f"Завтра у вас запись в {SALON_NAME}:\n"
                f"\U0001f4c5 {display_date} в {row['start_time']}\n"
                f"\U0001f485 {services}"
            )
            try:
                await context.bot.send_message(row["telegram_id"], text, parse_mode="HTML")
                mark_reminder_sent(row["id"], "day")
            except Exception:
                logger.exception("day reminder failed booking %s", row["id"])

        elif not row["reminder_hour_sent"] and 0.75 <= hours_left <= 1.25:
            text = (
                f"\U0001f514 <b>Напоминание</b>\n\n"
                f"Через час у вас запись в {SALON_NAME}:\n"
                f"\U0001f4c5 {display_date} в {row['start_time']}\n"
                f"\U0001f485 {services}"
            )
            try:
                await context.bot.send_message(row["telegram_id"], text, parse_mode="HTML")
                mark_reminder_sent(row["id"], "hour")
            except Exception:
                logger.exception("hour reminder failed booking %s", row["id"])
