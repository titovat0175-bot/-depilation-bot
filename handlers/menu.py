from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from config import SALON_ADDRESS, SALON_HOURS, SALON_NAME, SALON_PHONE, is_admin
from data.services import FAQ, SERVICES

BOOK_BTN = "\U0001f4c5 \u0417\u0430\u043f\u0438\u0441\u0430\u0442\u044c\u0441\u044f"
SERVICES_BTN = "\U0001f485 \u0423\u0441\u043b\u0443\u0433\u0438 \u0438 \u0446\u0435\u043d\u044b"
CONTACTS_BTN = "\U0001f4cd \u041a\u043e\u043d\u0442\u0430\u043a\u0442\u044b"
FAQ_BTN = "\u2753 \u0412\u043e\u043f\u0440\u043e\u0441\u044b \u0438 \u043e\u0442\u0432\u0435\u0442\u044b"
MY_BOOKINGS_BTN = "\U0001f4cb \u041c\u043e\u0438 \u0437\u0430\u043f\u0438\u0441\u0438"
ADMIN_BTN = "\U0001f464 \u041f\u0430\u043d\u0435\u043b\u044c \u043c\u0430\u0441\u0442\u0435\u0440\u0430"


def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    if is_admin(user_id):
        return ReplyKeyboardMarkup([[ADMIN_BTN]], resize_keyboard=True)
    return ReplyKeyboardMarkup(
        [
            [SERVICES_BTN, BOOK_BTN],
            [CONTACTS_BTN, FAQ_BTN],
            [MY_BOOKINGS_BTN],
        ],
        resize_keyboard=True,
    )


MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [[SERVICES_BTN, BOOK_BTN], [CONTACTS_BTN, FAQ_BTN], [MY_BOOKINGS_BTN]],
    resize_keyboard=True,
)


def main_menu_text(user_id: int) -> str:
    if is_admin(user_id):
        return (
            f"\U0001f464 <b>\u041f\u0430\u043d\u0435\u043b\u044c \u043c\u0430\u0441\u0442\u0435\u0440\u0430</b> \u00b7 {SALON_NAME}\n\n"
            "\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u043a\u043d\u043e\u043f\u043a\u0443 \u043d\u0438\u0436\u0435, \u0447\u0442\u043e\u0431\u044b \u0443\u043f\u0440\u0430\u0432\u043b\u044f\u0442\u044c \u0437\u0430\u043f\u0438\u0441\u044f\u043c\u0438 \U0001f447"
        )
    return (
        f"\u0414\u043e\u0431\u0440\u043e \u043f\u043e\u0436\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0432 <b>{SALON_NAME}</b>! \u2728\n\n"
        "\u041c\u044b \u0434\u0435\u043b\u0430\u0435\u043c \u0434\u0435\u043f\u0438\u043b\u044f\u0446\u0438\u044e \u0432\u043e\u0441\u043a\u043e\u043c \u0438 \u0448\u0443\u0433\u0430\u0440\u0438\u043d\u0433\u043e\u043c.\n\n"
        "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0440\u0430\u0437\u0434\u0435\u043b \u0432 \u043c\u0435\u043d\u044e \u043d\u0438\u0436\u0435 \U0001f447"
    )


def cancellation_client_text(
    booking_id: int,
    display_date: str,
    start_time: str,
    *,
    by_master: bool = False,
) -> str:
    if by_master:
        header = f"\u274c \u0412\u0430\u0448\u0430 \u0437\u0430\u043f\u0438\u0441\u044c <b>#{booking_id}</b> \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430 \u043c\u0430\u0441\u0442\u0435\u0440\u043e\u043c."
    else:
        header = f"\u2705 \u0417\u0430\u043f\u0438\u0441\u044c <b>#{booking_id}</b> \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430."
    return (
        f"{header}\n"
        f"\U0001f4c5 {display_date} \u0432 {start_time}\n\n"
        f"\u0416\u0430\u043b\u044c, \u0447\u0442\u043e \u043d\u0435 \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u0441\u044f \u0432\u0441\u0442\u0440\u0435\u0442\u0438\u0442\u044c\u0441\u044f \u0432 \u044d\u0442\u043e\u0442 \u0440\u0430\u0437 \U0001f4ab\n"
        f"\u041d\u043e \u043c\u044b \u0431\u0443\u0434\u0435\u043c \u043e\u0447\u0435\u043d\u044c \u0440\u0430\u0434\u044b \u0432\u0438\u0434\u0435\u0442\u044c \u0432\u0430\u0441 \u0432 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0439 \u0440\u0430\u0437! \U0001f496\n\n"
        f"\u041a\u043e\u0433\u0434\u0430 \u0437\u0430\u0445\u043e\u0442\u0438\u0442\u0435 \u0441\u043d\u043e\u0432\u0430 \u043f\u043e\u0431\u0430\u043b\u043e\u0432\u0430\u0442\u044c \u0441\u0435\u0431\u044f \u2014 \u0437\u0430\u043f\u0438\u0441\u044b\u0432\u0430\u0439\u0442\u0435\u0441\u044c, \u043c\u044b \u0432\u0441\u0435\u0433\u0434\u0430 \u0440\u044f\u0434\u043e\u043c \U0001f338\u2728"
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\U0001f4c5 \u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0441\u0435\u0433\u043e\u0434\u043d\u044f", callback_data="adm:today")],
        [InlineKeyboardButton("\U0001f4c6 \u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043d\u0430 \u0434\u0430\u0442\u0443", callback_data="adm:pick_date")],
        [InlineKeyboardButton("\u270f\ufe0f \u0423\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435 \u0437\u0430\u043f\u0438\u0441\u044f\u043c\u0438", callback_data="adm:edit")],
        [InlineKeyboardButton("\U0001f6ab \u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0434\u0435\u043d\u044c", callback_data="adm:block_day")],
        [InlineKeyboardButton("\u23f0 \u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0432\u0440\u0435\u043c\u044f", callback_data="adm:block_time")],
        [InlineKeyboardButton("\U0001f465 \u0411\u0430\u0437\u0430 \u043a\u043b\u0438\u0435\u043d\u0442\u043e\u0432", callback_data="adm:clients")],
        [InlineKeyboardButton("\U0001f4cb \u0411\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0438", callback_data="adm:blocks")],
    ])


def services_text() -> str:
    lines = ["<b>\U0001f485 \u0423\u0441\u043b\u0443\u0433\u0438 \u0438 \u0446\u0435\u043d\u044b</b>\n"]
    for service in SERVICES.values():
        lines.append(f"\u2022 <b>{service['name']}</b>\n  {service['price']} \u20bd \u00b7 {service['duration']}")
    lines.append("\n<i>\u041c\u043e\u0436\u043d\u043e \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0443\u0441\u043b\u0443\u0433 \u043f\u0440\u0438 \u0437\u0430\u043f\u0438\u0441\u0438</i>")
    return "\n".join(lines)


def contacts_text() -> str:
    return (
        f"<b>\U0001f4cd \u041a\u043e\u043d\u0442\u0430\u043a\u0442\u044b</b>\n\n"
        f"\U0001f3e0 <b>\u0410\u0434\u0440\u0435\u0441:</b> {SALON_ADDRESS}\n"
        f"\U0001f4de <b>\u0422\u0435\u043b\u0435\u0444\u043e\u043d:</b> {SALON_PHONE}\n"
        f"\U0001f550 <b>\u0420\u0435\u0436\u0438\u043c \u0440\u0430\u0431\u043e\u0442\u044b:</b> {SALON_HOURS}"
    )


def faq_text() -> str:
    lines = ["<b>\u2753 \u0427\u0430\u0441\u0442\u044b\u0435 \u0432\u043e\u043f\u0440\u043e\u0441\u044b</b>\n"]
    for question, answer in FAQ:
        lines.append(f"<b>{question}</b>\n{answer}\n")
    return "\n".join(lines)


def multi_service_keyboard(selected: set[str]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            f"{'\u2705 ' if key in selected else ''}{service['name']}",
            callback_data=f"svc:{key}",
        )]
        for key, service in SERVICES.items()
    ]
    buttons.append([InlineKeyboardButton("\u27a1\ufe0f \u0414\u0430\u043b\u0435\u0435", callback_data="svc_done")])
    buttons.append([InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="cancel_booking")])
    return InlineKeyboardMarkup(buttons)


def selection_summary(selected: set[str]) -> str:
    if not selected:
        return "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0443\u0441\u043b\u0443\u0433\u0438 (\u043c\u043e\u0436\u043d\u043e \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e):"
    from database.db import calc_totals
    price, duration, items = calc_totals(sorted(selected))
    lines = ["<b>\u0412\u044b\u0431\u0440\u0430\u043d\u043e:</b>"]
    for item in items:
        lines.append(f"\u2022 {item['name']} \u2014 {item['price']} \u20bd")
    lines.append(f"\n<b>\u0418\u0442\u043e\u0433\u043e:</b> {price} \u20bd \u00b7 ~{duration} \u043c\u0438\u043d")
    lines.append("\n\u041d\u0430\u0436\u043c\u0438\u0442\u0435 \u00ab\u0414\u0430\u043b\u0435\u0435\u00bb \u043a\u043e\u0433\u0434\u0430 \u0433\u043e\u0442\u043e\u0432\u044b:")
    return "\n".join(lines)


def times_keyboard(times: list[str]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for time_value in times:
        row.append(InlineKeyboardButton(time_value, callback_data=f"time:{time_value}"))
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("\u2b05\ufe0f \u041a \u0434\u0430\u0442\u0435", callback_data="back_date"),
        InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="cancel_booking"),
    ])
    return InlineKeyboardMarkup(rows)


def back_to_time_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2b05\ufe0f \u041a \u0432\u044b\u0431\u043e\u0440\u0443 \u0432\u0440\u0435\u043c\u0435\u043d\u0438", callback_data="back_time")],
    ])


def back_to_name_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u2b05\ufe0f \u041a \u0438\u043c\u0435\u043d\u0438", callback_data="back_name")],
        [InlineKeyboardButton("\u2b05\ufe0f \u041a \u0432\u0440\u0435\u043c\u0435\u043d\u0438", callback_data="back_time")],
    ])
