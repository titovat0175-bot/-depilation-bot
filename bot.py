import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import BOT_TOKEN, SALON_NAME
from database.db import init_db
from handlers.admin import build_admin_handlers
from handlers.booking import build_booking_handler, client_cancel_booking, my_bookings
from handlers.menu import (
    CONTACTS_BTN,
    FAQ_BTN,
    MY_BOOKINGS_BTN,
    SERVICES_BTN,
    contacts_text,
    faq_text,
    get_main_keyboard,
    main_menu_text,
    services_text,
)
from handlers.reminders import check_reminders

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_text(
        main_menu_text(user.id),
        parse_mode="HTML",
        reply_markup=get_main_keyboard(user.id),
    )


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == SERVICES_BTN:
        await update.message.reply_text(services_text(), parse_mode="HTML")
    elif text == CONTACTS_BTN:
        await update.message.reply_text(contacts_text(), parse_mode="HTML")
    elif text == FAQ_BTN:
        await update.message.reply_text(faq_text(), parse_mode="HTML")
    elif text == MY_BOOKINGS_BTN:
        await my_bookings(update, context)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("handler error", exc_info=context.error)


def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        logger.error("BOT_TOKEN не задан. Добавьте переменную BOT_TOKEN в Bothost.")
        sys.exit(1)

    logger.info("BOT_TOKEN найден (%s...)", BOT_TOKEN[:8])

    try:
        init_db()
        logger.info("База данных готова")
    except Exception:
        logger.exception("Ошибка инициализации базы данных")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    for handler in build_admin_handlers():
        app.add_handler(handler)
    app.add_handler(build_booking_handler())
    app.add_handler(CallbackQueryHandler(client_cancel_booking, pattern=r"^cl_cancel:"))
    app.add_handler(
        MessageHandler(
            filters.Regex(f"^({SERVICES_BTN}|{CONTACTS_BTN}|{FAQ_BTN}|{MY_BOOKINGS_BTN})$"),
            handle_menu,
        )
    )
    app.add_error_handler(on_error)

    if app.job_queue:
        app.job_queue.run_repeating(check_reminders, interval=300, first=15)
    else:
        logger.warning("JobQueue unavailable - check APScheduler in requirements.txt")

    logger.info("Bot %s started, polling...", SALON_NAME)
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()
