import calendar
from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from salon_data.services import BOOKING_DAYS_AHEAD

MONTH_NAMES = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month += delta
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def _month_bounds(today: date) -> tuple[date, date]:
    return today, today + timedelta(days=BOOKING_DAYS_AHEAD)


def parse_cal_nav(data: str) -> tuple[int, int] | None:
    if data.startswith("cal:p:"):
        year, month = map(int, data.removeprefix("cal:p:").split("-"))
        return _shift_month(year, month, -1)
    if data.startswith("cal:n:"):
        year, month = map(int, data.removeprefix("cal:n:").split("-"))
        return _shift_month(year, month, 1)
    return None


def parse_admin_cal_nav(data: str) -> tuple[int, int, str] | None:
    if not (data.startswith("acal:p:") or data.startswith("acal:n:")):
        return None
    parts = data.split(":")
    delta = -1 if parts[1] == "p" else 1
    year, month = map(int, parts[2].split("-"))
    action = parts[3]
    year, month = _shift_month(year, month, delta)
    return year, month, action


def calendar_keyboard(
    year: int,
    month: int,
    available_dates: set[str],
    *,
    cancel_callback: str = "cancel_booking",
    back_callback: str | None = None,
) -> InlineKeyboardMarkup:
    today = date.today()
    min_date, max_date = _month_bounds(today)
    rows: list[list[InlineKeyboardButton]] = []

    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    prev_end = date(prev_year, prev_month, calendar.monthrange(prev_year, prev_month)[1])
    next_start = date(next_year, next_month, 1)

    nav_row: list[InlineKeyboardButton] = []
    if prev_end >= min_date:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"cal:p:{year:04d}-{month:02d}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="cal:x"))
    nav_row.append(InlineKeyboardButton(f"{MONTH_NAMES[month - 1]} {year}", callback_data="cal:x"))
    if next_start <= max_date:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"cal:n:{year:04d}-{month:02d}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="cal:x"))
    rows.append(nav_row)
    rows.append([InlineKeyboardButton(day, callback_data="cal:x") for day in WEEKDAYS])

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day.month != month:
                row.append(InlineKeyboardButton("·", callback_data="cal:x"))
                continue
            day_str = day.strftime("%d.%m.%Y")
            if day < today or day > max_date or day_str not in available_dates:
                row.append(InlineKeyboardButton("·", callback_data="cal:x"))
            else:
                row.append(InlineKeyboardButton(str(day.day), callback_data=f"date:{day_str}"))
        rows.append(row)

    if back_callback:
        rows.append([InlineKeyboardButton("⬅️ К услугам", callback_data=back_callback)])
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data=cancel_callback)])
    return InlineKeyboardMarkup(rows)


_DAY_STATUS_EMOJI = {
    "free": "🟢",
    "partial": "🟡",
    "full": "🔴",
}


def admin_calendar_keyboard(
    year: int,
    month: int,
    action_prefix: str,
    day_status: dict[str, str],
    *,
    back_callback: str = "adm:home",
) -> InlineKeyboardMarkup:
    today = date.today()
    min_date, max_date = _month_bounds(today)
    rows: list[list[InlineKeyboardButton]] = []

    prev_year, prev_month = _shift_month(year, month, -1)
    next_year, next_month = _shift_month(year, month, 1)
    prev_end = date(prev_year, prev_month, calendar.monthrange(prev_year, prev_month)[1])
    next_start = date(next_year, next_month, 1)

    nav_row: list[InlineKeyboardButton] = []
    if prev_end >= min_date:
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"acal:p:{year:04d}-{month:02d}:{action_prefix}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="cal:x"))
    nav_row.append(InlineKeyboardButton(f"{MONTH_NAMES[month - 1]} {year}", callback_data="cal:x"))
    if next_start <= max_date:
        nav_row.append(InlineKeyboardButton("▶️", callback_data=f"acal:n:{year:04d}-{month:02d}:{action_prefix}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="cal:x"))
    rows.append(nav_row)
    rows.append([InlineKeyboardButton(day, callback_data="cal:x") for day in WEEKDAYS])
    rows.append([
        InlineKeyboardButton("🟢", callback_data="cal:x"),
        InlineKeyboardButton("🟡", callback_data="cal:x"),
        InlineKeyboardButton("🔴", callback_data="cal:x"),
    ])

    cal = calendar.Calendar(firstweekday=0)
    for week in cal.monthdatescalendar(year, month):
        row: list[InlineKeyboardButton] = []
        for day in week:
            if day.month != month:
                row.append(InlineKeyboardButton("·", callback_data="cal:x"))
                continue
            if day < today or day > max_date:
                row.append(InlineKeyboardButton("·", callback_data="cal:x"))
                continue
            day_str = day.strftime("%d.%m.%Y")
            status = day_status.get(day_str, "free")
            emoji = _DAY_STATUS_EMOJI.get(status)
            label = f"{emoji}{day.day}" if emoji else str(day.day)
            row.append(InlineKeyboardButton(label, callback_data=f"{action_prefix}:{day_str}"))
        rows.append(row)

    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(rows)
