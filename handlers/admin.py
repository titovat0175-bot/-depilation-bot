from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from config import is_admin
from salon_data.services import SERVICES
from database.db import (
    _booking_duration_minutes,
    add_service_to_booking,
    block_full_day,
    block_time_range,
    cancel_booking,
    get_available_times,
    get_booking_by_id,
    get_booking_service_keys,
    get_bookings_for_date,
    get_calendar_status_for_month,
    list_blocked_days,
    list_clients,
    parse_display_date,
    remove_service_from_booking,
    update_booking_time,
)
from handlers.calendar import admin_calendar_keyboard, parse_admin_cal_nav
from handlers.menu import ADMIN_BTN, admin_panel_keyboard, cancellation_client_text

ADMIN_BLOCK_TIME_DATE, ADMIN_BLOCK_TIME_START, ADMIN_BLOCK_TIME_END = range(3)

_ADMIN_CAL_TITLES = {
    "adm_sd": "📅 <b>Расписание на дату</b>\n\n🟢 свободный · 🟡 частично занят · 🔴 полностью занят\nВыберите дату:",
    "adm_ed": "✏️ <b>Редактирование записей</b>\n\n🟢 свободный · 🟡 частично занят · 🔴 полностью занят\nВыберите дату:",
    "adm_bd": "🚫 <b>Блокировка дня</b>\n\n🟢 свободный · 🟡 частично занят · 🔴 полностью занят\nВыберите дату:",
    "adm_bt_d": "⏰ <b>Блокировка времени</b>\n\n🟢 свободный · 🟡 частично занят · 🔴 полностью занят\nВыберите дату:",
}


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text(
        "<b>👤 Панель мастера</b>",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


async def _show_admin_calendar(
    query,
    action_prefix: str,
    year: int | None = None,
    month: int | None = None,
    *,
    back_callback: str = "adm:home",
) -> None:
    today = date.today()
    year = year or today.year
    month = month or today.month
    day_status = get_calendar_status_for_month(year, month)
    title = _ADMIN_CAL_TITLES.get(action_prefix, "Выберите дату:")
    await query.edit_message_text(
        title,
        parse_mode="HTML",
        reply_markup=admin_calendar_keyboard(
            year, month, action_prefix, day_status, back_callback=back_callback
        ),
    )


async def admin_calendar_nav(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query.data == "cal:x":
        await query.answer()
        return
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    parsed = parse_admin_cal_nav(query.data)
    if not parsed:
        return
    year, month, action = parsed
    back = "adm:edit" if action == "adm_ed" else "adm:home"
    await _show_admin_calendar(query, action, year, month, back_callback=back)


def _booking_detail_text(row) -> str:
    display_date = date.fromisoformat(row["date"]).strftime("%d.%m.%Y")
    return (
        f"<b>Запись #{row['id']}</b>\n\n"
        f"👤 {row['name']} ({row['phone']})\n"
        f"📅 {display_date} {row['start_time']}–{row['end_time']}\n"
        f"💅 {row['services']}\n"
        f"💰 {row['total_price']} ₽"
    )


def _booking_edit_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ Изменить время", callback_data=f"adm_et:{booking_id}")],
        [InlineKeyboardButton("➕ Добавить услугу", callback_data=f"adm_ea:{booking_id}")],
        [InlineKeyboardButton("➖ Убрать услугу", callback_data=f"adm_er:{booking_id}")],
        [InlineKeyboardButton("❌ Отменить запись", callback_data=f"adm_ec:{booking_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="adm:edit")],
    ])


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Нет доступа.")
        return ConversationHandler.END
    action = query.data.removeprefix("adm:")
    today = date.today()

    if action == "home":
        await query.edit_message_text(
            "<b>👤 Панель мастера</b>",
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )
        return None
    if action == "today":
        rows = get_bookings_for_date(today)
        if not rows:
            text = f"<b>Расписание на {today.strftime('%d.%m.%Y')}</b>\n\nЗаписей нет."
        else:
            lines = [f"<b>Расписание на {today.strftime('%d.%m.%Y')}</b>\n"]
            for row in rows:
                lines.append(f"• {row['start_time']}–{row['end_time']} — {row['name']}\n  {row['services']} ({row['phone']})")
            text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="adm:home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return None
    if action == "pick_date":
        await _show_admin_calendar(query, "adm_sd", today.year, today.month)
        return None
    if action == "edit":
        await _show_admin_calendar(query, "adm_ed", today.year, today.month, back_callback="adm:home")
        return None
    if action == "clients":
        rows = list_clients()
        if not rows:
            text = "База клиентов пуста."
        else:
            lines = ["<b>👥 Клиенты</b>\n"]
            for row in rows:
                lines.append(f"• {row['name']} — {row['phone']}\n  TG: {row['telegram_id']}, записей: {row['bookings_count']}")
            text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="adm:home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return None
    if action == "blocks":
        rows = list_blocked_days()
        if not rows:
            text = "Активных блокировок нет."
        else:
            lines = ["<b>📋 Блокировки</b>\n"]
            for row in rows:
                if row["start_time"] is None:
                    lines.append(f"• {row['date']} — весь день")
                else:
                    lines.append(f"• {row['date']} {row['start_time']}–{row['end_time']}")
            text = "\n".join(lines)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="adm:home")]])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        return None
    if action == "block_day":
        await _show_admin_calendar(query, "adm_bd", today.year, today.month)
        return None
    if action == "block_time":
        await _show_admin_calendar(query, "adm_bt_d", today.year, today.month)
        return ADMIN_BLOCK_TIME_DATE
    if action == "cancel":
        await query.edit_message_text("Отменено.")
        return ConversationHandler.END
    return None


async def admin_schedule_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    day_str = query.data.removeprefix("adm_sd:")
    day = parse_display_date(day_str)
    rows = get_bookings_for_date(day)
    if not rows:
        text = f"<b>Расписание на {day_str}</b>\n\nЗаписей нет."
    else:
        lines = [f"<b>Расписание на {day_str}</b>\n"]
        for row in rows:
            lines.append(f"• #{row['id']} {row['start_time']}–{row['end_time']} — {row['name']}\n  {row['services']}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="adm:pick_date")]])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def admin_edit_pick_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    day_str = query.data.removeprefix("adm_ed:")
    day = parse_display_date(day_str)
    rows = get_bookings_for_date(day)
    if not rows:
        await query.edit_message_text(f"На {day_str} записей нет.")
        return
    buttons = [[InlineKeyboardButton(
        f"#{row['id']} {row['start_time']} {row['name']}",
        callback_data=f"adm_eb:{row['id']}",
    )] for row in rows]
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="adm:edit")])
    await query.edit_message_text(
        f"Записи на {day_str}:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def admin_edit_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    data = query.data
    if data.startswith("adm_eb:"):
        booking_id = int(data.removeprefix("adm_eb:"))
        row = get_booking_by_id(booking_id)
        if not row:
            await query.edit_message_text("Запись не найдена.")
            return
        await query.edit_message_text(_booking_detail_text(row), parse_mode="HTML", reply_markup=_booking_edit_keyboard(booking_id))
        return
    if data.startswith("adm_ec:"):
        booking_id = int(data.removeprefix("adm_ec:"))
        row = cancel_booking(booking_id)
        if not row:
            await query.answer("Уже отменена", show_alert=True)
            return
        display_date = date.fromisoformat(row["date"]).strftime("%d.%m.%Y")
        await query.edit_message_text(f"✅ Запись #{booking_id} отменена.")
        try:
            await context.bot.send_message(
                row["telegram_id"],
                cancellation_client_text(
                    booking_id, display_date, row["start_time"], by_master=True
                ),
                parse_mode="HTML",
            )
        except Exception:
            pass
        return
    if data.startswith("adm_ett:"):
        rest = data.removeprefix("adm_ett:")
        booking_id_str, new_time = rest.split(":", 1)
        booking_id = int(booking_id_str)
        if update_booking_time(booking_id, new_time):
            row = get_booking_by_id(booking_id)
            await query.edit_message_text(f"✅ Время изменено: {new_time}", reply_markup=_booking_edit_keyboard(booking_id))
            if row:
                try:
                    display_date = date.fromisoformat(row["date"]).strftime("%d.%m.%Y")
                    await context.bot.send_message(
                        row["telegram_id"],
                        f"🔔 Время вашей записи #{booking_id} изменено:\n{display_date} {new_time}",
                    )
                except Exception:
                    pass
        else:
            await query.answer("Не удалось изменить время", show_alert=True)
        return
    if data.startswith("adm_et:"):
        booking_id = int(data.removeprefix("adm_et:"))
        row = get_booking_by_id(booking_id)
        if not row:
            return
        day = date.fromisoformat(row["date"])
        duration = _booking_duration_minutes(booking_id)
        times = get_available_times(day, duration, exclude_booking_id=booking_id)
        if not times:
            await query.answer("Нет свободного времени", show_alert=True)
            return
        buttons = [[InlineKeyboardButton(t, callback_data=f"adm_ett:{booking_id}:{t}")] for t in times]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_eb:{booking_id}")])
        await query.edit_message_text("Выберите новое время:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data.startswith("adm_eas:"):
        _, rest = data.split(":", 1)
        booking_id_str, service_key = rest.split(":", 1)
        booking_id = int(booking_id_str)
        if add_service_to_booking(booking_id, service_key):
            row = get_booking_by_id(booking_id)
            await query.edit_message_text("✅ Услуга добавлена.", reply_markup=_booking_edit_keyboard(booking_id))
            if row:
                try:
                    await context.bot.send_message(
                        row["telegram_id"],
                        f"🔔 К записи #{booking_id} добавлена услуга: {SERVICES[service_key]['name']}",
                    )
                except Exception:
                    pass
        else:
            await query.answer("Не удалось добавить", show_alert=True)
        return
    if data.startswith("adm_ea:"):
        booking_id = int(data.removeprefix("adm_ea:"))
        current = set(get_booking_service_keys(booking_id))
        buttons = [
            [InlineKeyboardButton(svc["name"], callback_data=f"adm_eas:{booking_id}:{key}")]
            for key, svc in SERVICES.items() if key not in current
        ]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_eb:{booking_id}")])
        await query.edit_message_text("Выберите услугу для добавления:", reply_markup=InlineKeyboardMarkup(buttons))
        return
    if data.startswith("adm_ers:"):
        _, rest = data.split(":", 1)
        booking_id_str, service_key = rest.split(":", 1)
        booking_id = int(booking_id_str)
        if remove_service_from_booking(booking_id, service_key):
            await query.edit_message_text("✅ Услуга убрана.", reply_markup=_booking_edit_keyboard(booking_id))
            row = get_booking_by_id(booking_id)
            if row:
                try:
                    await context.bot.send_message(
                        row["telegram_id"],
                        f"🔔 Из записи #{booking_id} убрана услуга: {SERVICES[service_key]['name']}",
                    )
                except Exception:
                    pass
        else:
            await query.answer("Не удалось убрать", show_alert=True)
        return
    if data.startswith("adm_er:"):
        booking_id = int(data.removeprefix("adm_er:"))
        current = get_booking_service_keys(booking_id)
        if len(current) <= 1:
            await query.answer("Должна остаться хотя бы одна услуга", show_alert=True)
            return
        buttons = [[InlineKeyboardButton(SERVICES[k]["name"], callback_data=f"adm_ers:{booking_id}:{k}")] for k in current]
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"adm_eb:{booking_id}")])
        await query.edit_message_text("Какую услугу убрать?", reply_markup=InlineKeyboardMarkup(buttons))


async def block_day_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    if query.data.startswith("adm_bd:"):
        day_str = query.data.removeprefix("adm_bd:")
        block_full_day(parse_display_date(day_str), "Выходной/отпуск")
        await query.edit_message_text(f"✅ День {day_str} заблокирован.")


async def block_time_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["block_date"] = query.data.removeprefix("adm_bt_d:")
    await query.edit_message_text("Введите время НАЧАЛА (ЧЧ:ММ), например 14:00")
    return ADMIN_BLOCK_TIME_START


async def block_time_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if len(value) != 5 or value[2] != ":":
        await update.message.reply_text("Формат ЧЧ:ММ")
        return ADMIN_BLOCK_TIME_START
    context.user_data["block_start"] = value
    await update.message.reply_text("Введите время КОНЦА (ЧЧ:ММ), например 16:00")
    return ADMIN_BLOCK_TIME_END


async def block_time_end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value = update.message.text.strip()
    if len(value) != 5 or value[2] != ":":
        await update.message.reply_text("Формат ЧЧ:ММ")
        return ADMIN_BLOCK_TIME_END
    day = parse_display_date(context.user_data["block_date"])
    block_time_range(day, context.user_data["block_start"], value, "Блок мастера")
    await update.message.reply_text(
        f"✅ Заблокировано: {context.user_data['block_date']} {context.user_data['block_start']}–{value}"
    )
    context.user_data.clear()
    return ConversationHandler.END


def build_admin_handlers():
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_callback, pattern=r"^adm:")],
        states={
            ADMIN_BLOCK_TIME_DATE: [CallbackQueryHandler(block_time_date, pattern=r"^adm_bt_d:")],
            ADMIN_BLOCK_TIME_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_time_start)],
            ADMIN_BLOCK_TIME_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_time_end)],
        },
        fallbacks=[CommandHandler("admin", admin_panel)],
        allow_reentry=True,
    )
    return [
        CommandHandler("admin", admin_panel),
        MessageHandler(filters.Regex(f"^{ADMIN_BTN}$"), admin_panel),
        CallbackQueryHandler(admin_calendar_nav, pattern=r"^acal:"),
        CallbackQueryHandler(block_day_pick, pattern=r"^adm_bd:"),
        CallbackQueryHandler(admin_schedule_date, pattern=r"^adm_sd:"),
        CallbackQueryHandler(admin_edit_pick_date, pattern=r"^adm_ed:"),
        CallbackQueryHandler(admin_edit_booking, pattern=r"^adm_e(?:tt|as|rs|b|c|t|a|r):"),
        conv,
    ]
