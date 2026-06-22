import logging
import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_IDS, SALON_NAME
from database.db import (
    calc_totals,
    cancel_booking_for_client,
    create_booking,
    get_available_dates,
    get_available_times,
    get_client_by_telegram,
    get_client_bookings,
    parse_display_date,
    upsert_client,
)
from handlers.calendar import calendar_keyboard, parse_cal_nav
from handlers.menu import (
    BOOK_BTN,
    back_to_name_keyboard,
    back_to_time_keyboard,
    cancellation_client_text,
    get_main_keyboard,
    multi_service_keyboard,
    selection_summary,
    times_keyboard,
)

logger = logging.getLogger(__name__)

SELECT_SERVICES, SELECT_DATE, SELECT_TIME, ENTER_NAME, ENTER_PHONE, CONFIRM = range(6)
PHONE_PATTERN = re.compile(r"^\+?[\d\s\-\(\)]{10,20}$")


def _available_dates_set(context: ContextTypes.DEFAULT_TYPE) -> set[str]:
    duration = context.user_data.get("total_duration", 30)
    return set(get_available_dates(duration))


async def _show_date_calendar(query, context: ContextTypes.DEFAULT_TYPE, year: int, month: int) -> None:
    selected = context.user_data.get("selected_services", set())
    summary = selection_summary(selected) if selected else ""
    text = f"{summary}\n\n<b>Выберите дату в календаре:</b>" if summary else "<b>Выберите дату в календаре:</b>"
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=calendar_keyboard(
            year, month, _available_dates_set(context), back_callback="back_services"
        ),
    )


async def _show_times(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    selected_date = context.user_data["date"]
    day = parse_display_date(selected_date)
    times = get_available_times(day, context.user_data["total_duration"])
    await query.edit_message_text(
        f"Дата: <b>{selected_date}</b>\n\nВыберите время:",
        parse_mode="HTML",
        reply_markup=times_keyboard(times),
    )


def _confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_booking")],
        [InlineKeyboardButton("⬅️ К времени", callback_data="back_time")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_booking")],
    ])


def _build_summary(data: dict) -> str:
    services_lines = "\n".join(f"• {i['name']} — {i['price']} ₽" for i in data["service_items"])
    return (
        f"✅ <b>Подтвердите запись</b>\n\n"
        f"👤 {data['client_name']}\n📞 {data['phone']}\n\n"
        f"<b>Услуги:</b>\n{services_lines}\n\n"
        f"💰 {data['total_price']} ₽ (~{data['total_duration']} мин)\n"
        f"📅 {data['date']} в {data['time']}"
    )


def _success_message(booking_id: int, data: dict, services_text: str) -> str:
    return (
        f"🎉 <b>Ура! Вы записаны!</b> 💖\n\n"
        f"Номер записи: <b>#{booking_id}</b> ✨\n"
        f"📅 {data['date']} в {data['time']}\n"
        f"💅 {services_text}\n"
        f"💰 {data['total_price']} ₽\n\n"
        f"Мы уже ждём вас в <b>{SALON_NAME}</b>! 🌸\n"
        f"Приходите отдохнуть и побаловать себя — вы этого заслужили! 💆‍♀️✨\n\n"
        f"До встречи! 🤗💕"
    )


async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    context.user_data["selected_services"] = set()
    await update.message.reply_text(
        selection_summary(set()),
        parse_mode="HTML",
        reply_markup=multi_service_keyboard(set()),
    )
    return SELECT_SERVICES


async def toggle_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_booking":
        await query.edit_message_text("Запись отменена.")
        await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(query.from_user.id))
        return ConversationHandler.END
    if query.data == "svc_done":
        selected = context.user_data.get("selected_services", set())
        if not selected:
            await query.answer("Выберите хотя бы одну услугу", show_alert=True)
            return SELECT_SERVICES
        price, duration, items = calc_totals(sorted(selected))
        context.user_data.update(total_price=price, total_duration=duration, service_items=items)
        dates = get_available_dates(duration)
        if not dates:
            await query.edit_message_text("К сожалению, свободных дат нет.")
            await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(query.from_user.id))
            return ConversationHandler.END
        today = date.today()
        await query.edit_message_text(
            f"{selection_summary(selected)}\n\n<b>Выберите дату в календаре:</b>",
            parse_mode="HTML",
            reply_markup=calendar_keyboard(
                today.year, today.month, set(dates), back_callback="back_services"
            ),
        )
        return SELECT_DATE
    key = query.data.removeprefix("svc:")
    selected = context.user_data.setdefault("selected_services", set())
    if key in selected:
        selected.remove(key)
    else:
        selected.add(key)
    await query.edit_message_text(
        selection_summary(selected),
        parse_mode="HTML",
        reply_markup=multi_service_keyboard(selected),
    )
    return SELECT_SERVICES


async def booking_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "cancel_booking":
        await query.edit_message_text("Запись отменена.")
        await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(query.from_user.id))
        return ConversationHandler.END

    if action == "back_services":
        selected = context.user_data.get("selected_services", set())
        await query.edit_message_text(
            selection_summary(selected),
            parse_mode="HTML",
            reply_markup=multi_service_keyboard(selected),
        )
        return SELECT_SERVICES

    if action == "back_date":
        today = date.today()
        await _show_date_calendar(query, context, today.year, today.month)
        return SELECT_DATE

    if action == "back_time":
        await _show_times(query, context)
        return SELECT_TIME

    if action == "back_name":
        await query.edit_message_text(
            f"Дата: {context.user_data['date']}, время: {context.user_data['time']}\n\nВведите ваше имя:",
            reply_markup=back_to_time_keyboard(),
        )
        return ENTER_NAME

    return ConversationHandler.END


async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query.data == "cal:x":
        await query.answer()
        return SELECT_DATE
    if query.data in ("back_services", "back_date", "back_time", "back_name", "cancel_booking"):
        return await booking_nav(update, context)
    await query.answer()

    nav = parse_cal_nav(query.data)
    if nav:
        year, month = nav
        await _show_date_calendar(query, context, year, month)
        return SELECT_DATE

    selected_date = query.data.removeprefix("date:")
    context.user_data["date"] = selected_date
    day = parse_display_date(selected_date)
    times = get_available_times(day, context.user_data["total_duration"])
    if not times:
        await query.answer("На эту дату нет свободного времени", show_alert=True)
        return SELECT_DATE
    await query.edit_message_text(
        f"Дата: <b>{selected_date}</b>\n\nВыберите время:",
        parse_mode="HTML",
        reply_markup=times_keyboard(times),
    )
    return SELECT_TIME


async def select_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query.data in ("back_date", "back_time", "back_name", "back_services", "cancel_booking"):
        return await booking_nav(update, context)
    await query.answer()

    context.user_data["time"] = query.data.removeprefix("time:")
    user = update.effective_user
    client = get_client_by_telegram(user.id)
    if client:
        context.user_data["client_name"] = client["name"]
        context.user_data["phone"] = client["phone"]
        return await show_confirmation(update, context, from_callback=True)

    await query.edit_message_text(
        f"Дата: {context.user_data['date']}, время: {context.user_data['time']}\n\nВведите ваше имя:",
        reply_markup=back_to_time_keyboard(),
    )
    return ENTER_NAME


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text(
            "Имя слишком короткое.",
            reply_markup=back_to_time_keyboard(),
        )
        return ENTER_NAME
    context.user_data["client_name"] = name
    await update.message.reply_text(
        "Введите номер телефона:\n<i>+7 999 123-45-67</i>",
        parse_mode="HTML",
        reply_markup=back_to_name_keyboard(),
    )
    return ENTER_PHONE


async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip()
    if not PHONE_PATTERN.match(phone):
        await update.message.reply_text(
            "Некорректный номер. Попробуйте ещё раз:",
            reply_markup=back_to_name_keyboard(),
        )
        return ENTER_PHONE
    context.user_data["phone"] = phone
    return await show_confirmation(update, context, from_callback=False)


async def show_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback: bool) -> int:
    text = _build_summary(context.user_data)
    keyboard = _confirmation_keyboard()
    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=keyboard)
    return CONFIRM


async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query.data in ("back_time", "back_date", "back_name", "back_services"):
        return await booking_nav(update, context)
    await query.answer()

    if query.data == "cancel_booking":
        await query.edit_message_text("Запись отменена.")
        await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(query.from_user.id))
        return ConversationHandler.END

    data = context.user_data
    user = update.effective_user
    day = parse_display_date(data["date"])
    times = get_available_times(day, data["total_duration"])
    if data["time"] not in times:
        await query.edit_message_text("Это время уже занято. Выберите другое.")
        await _show_times(query, context)
        return SELECT_TIME

    client_id = upsert_client(user.id, data["client_name"], data["phone"])
    booking_id = create_booking(
        client_id, day, data["time"], data["total_duration"], data["total_price"], data["service_items"]
    )
    services_text = ", ".join(i["name"] for i in data["service_items"])
    await query.edit_message_text(
        _success_message(booking_id, data, services_text),
        parse_mode="HTML",
    )
    await query.message.reply_text("Главное меню:", reply_markup=get_main_keyboard(user.id))

    admin_text = (
        f"🆕 <b>Новая запись #{booking_id}</b>\n\n"
        f"👤 {data['client_name']}\n📞 {data['phone']}\n"
        f"💅 {services_text}\n💰 {data['total_price']} ₽\n"
        f"📅 {data['date']} в {data['time']}\n"
        f"🆔 @{user.username or '—'} (id: {user.id})"
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception:
            logger.exception("admin notify %s", admin_id)
    context.user_data.clear()
    return ConversationHandler.END


async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    rows = get_client_bookings(user_id)
    if not rows:
        await update.message.reply_text("У вас нет активных записей.")
        return
    lines = ["<b>📋 Ваши записи:</b>\n"]
    buttons = []
    for row in rows:
        display_date = date.fromisoformat(row["date"]).strftime("%d.%m.%Y")
        lines.append(
            f"• <b>#{row['id']}</b> — {display_date} {row['start_time']}\n"
            f"  {row['services']} ({row['total_price']} ₽)"
        )
        buttons.append([InlineKeyboardButton(
            f"❌ Отменить #{row['id']}",
            callback_data=f"cl_cancel:{row['id']}",
        )])
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def client_cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    booking_id = int(query.data.removeprefix("cl_cancel:"))
    row = cancel_booking_for_client(booking_id, query.from_user.id)
    if not row:
        await query.answer("Запись не найдена", show_alert=True)
        return
    display_date = date.fromisoformat(row["date"]).strftime("%d.%m.%Y")
    await query.edit_message_text(
        cancellation_client_text(booking_id, display_date, row["start_time"]),
        parse_mode="HTML",
    )
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"❌ Клиент отменил запись #{booking_id}\n{display_date} {row['start_time']}",
            )
        except Exception:
            logger.exception("admin cancel notify")


async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    uid = update.effective_user.id
    await update.message.reply_text("Запись отменена.", reply_markup=get_main_keyboard(uid))
    return ConversationHandler.END


_NAV_PATTERN = r"^(back_services|back_date|back_time|back_name|cancel_booking)$"


def build_booking_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BOOK_BTN)}$"), start_booking)],
        states={
            SELECT_SERVICES: [CallbackQueryHandler(toggle_service, pattern=r"^(svc:|svc_done|cancel_booking)")],
            SELECT_DATE: [CallbackQueryHandler(select_date, pattern=r"^(date:|cal:|back_|cancel_booking)")],
            SELECT_TIME: [CallbackQueryHandler(select_time, pattern=r"^(time:|back_|cancel_booking)")],
            ENTER_NAME: [
                CallbackQueryHandler(booking_nav, pattern=_NAV_PATTERN),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name),
            ],
            ENTER_PHONE: [
                CallbackQueryHandler(booking_nav, pattern=_NAV_PATTERN),
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone),
            ],
            CONFIRM: [CallbackQueryHandler(confirm_booking, pattern=r"^(confirm_booking|back_|cancel_booking)")],
        },
        fallbacks=[CommandHandler("cancel", cancel_booking)],
        allow_reentry=True,
    )
