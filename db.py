import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

from data.services import BOOKING_DAYS_AHEAD, SERVICES, SLOT_STEP_MIN

DB_PATH = Path(__file__).parent.parent / "data" / "salon.db"


def _time_to_minutes(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def _minutes_to_time(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def _parse_display_date(value: str) -> date:
    return datetime.strptime(value, "%d.%m.%Y").date()


def _format_display_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _format_db_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def _booking_duration_minutes(booking_id: int) -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(duration_min), 0) AS d FROM booking_services WHERE booking_id = ?",
            (booking_id,),
        ).fetchone()
        return int(row["d"])


@contextmanager
def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bookings)")}
    if "reminder_day_sent" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN reminder_day_sent INTEGER DEFAULT 0")
    if "reminder_hour_sent" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN reminder_hour_sent INTEGER DEFAULT 0")


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                total_price INTEGER NOT NULL,
                status TEXT DEFAULT 'confirmed',
                reminder_day_sent INTEGER DEFAULT 0,
                reminder_hour_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );

            CREATE TABLE IF NOT EXISTS booking_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                service_key TEXT NOT NULL,
                service_name TEXT NOT NULL,
                price INTEGER NOT NULL,
                duration_min INTEGER NOT NULL,
                FOREIGN KEY (booking_id) REFERENCES bookings(id)
            );

            CREATE TABLE IF NOT EXISTS blocked_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                reason TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS work_schedule (
                weekday INTEGER PRIMARY KEY,
                is_working INTEGER DEFAULT 1,
                start_time TEXT DEFAULT '10:00',
                end_time TEXT DEFAULT '20:00'
            );
            """
        )
        _migrate(conn)
        existing = conn.execute("SELECT COUNT(*) AS c FROM work_schedule").fetchone()["c"]
        if existing == 0:
            rows = [(w, 0 if w == 6 else 1, "10:00", "20:00") for w in range(7)]
            conn.executemany(
                "INSERT INTO work_schedule (weekday, is_working, start_time, end_time) VALUES (?, ?, ?, ?)",
                rows,
            )


def get_work_day(weekday: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM work_schedule WHERE weekday = ?", (weekday,)).fetchone()


def is_day_blocked(day: date) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM blocked_slots WHERE date = ? AND start_time IS NULL LIMIT 1",
            (_format_db_date(day),),
        ).fetchone()
        return row is not None


def _get_busy_ranges(db_date: str, exclude_booking_id: int | None = None) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    with get_conn() as conn:
        query = "SELECT id, start_time, end_time FROM bookings WHERE date = ? AND status = 'confirmed'"
        params: list = [db_date]
        rows = conn.execute(query, params).fetchall()
        for row in rows:
            if exclude_booking_id and row["id"] == exclude_booking_id:
                continue
            ranges.append((_time_to_minutes(row["start_time"]), _time_to_minutes(row["end_time"])))
        for row in conn.execute(
            "SELECT start_time, end_time FROM blocked_slots WHERE date = ? AND start_time IS NOT NULL",
            (db_date,),
        ):
            end = row["end_time"] or row["start_time"]
            ranges.append((_time_to_minutes(row["start_time"]), _time_to_minutes(end)))
    return ranges


def _fits_schedule(day: date, start_min: int, end_min: int) -> bool:
    schedule = get_work_day(day.weekday())
    if not schedule or not schedule["is_working"]:
        return False
    return start_min >= _time_to_minutes(schedule["start_time"]) and end_min <= _time_to_minutes(schedule["end_time"])


def is_slot_available(day: date, start_time: str, duration_min: int, exclude_booking_id: int | None = None) -> bool:
    if is_day_blocked(day):
        return False
    start_min = _time_to_minutes(start_time)
    end_min = start_min + duration_min
    if not _fits_schedule(day, start_min, end_min):
        return False
    for busy_start, busy_end in _get_busy_ranges(_format_db_date(day), exclude_booking_id):
        if start_min < busy_end and busy_start < end_min:
            return False
    return True


def get_available_dates(duration_min: int, days_ahead: int = BOOKING_DAYS_AHEAD, exclude_booking_id: int | None = None) -> list[str]:
    today = date.today()
    result: list[str] = []
    for offset in range(days_ahead):
        day = today + timedelta(days=offset)
        schedule = get_work_day(day.weekday())
        if not schedule or not schedule["is_working"] or is_day_blocked(day):
            continue
        if get_available_times(day, duration_min, exclude_booking_id):
            result.append(_format_display_date(day))
    return result


def get_available_times(day: date, duration_min: int, exclude_booking_id: int | None = None) -> list[str]:
    if is_day_blocked(day):
        return []
    schedule = get_work_day(day.weekday())
    if not schedule or not schedule["is_working"]:
        return []
    work_start = _time_to_minutes(schedule["start_time"])
    work_end = _time_to_minutes(schedule["end_time"])
    busy_ranges = _get_busy_ranges(_format_db_date(day), exclude_booking_id)
    available: list[str] = []
    current = work_start
    while current + duration_min <= work_end:
        end = current + duration_min
        overlap = any(current < busy_end and busy_start < end for busy_start, busy_end in busy_ranges)
        if not overlap:
            available.append(_minutes_to_time(current))
        current += SLOT_STEP_MIN
    return available


def upsert_client(telegram_id: int, name: str, phone: str) -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM clients WHERE telegram_id = ?", (telegram_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE clients SET name = ?, phone = ?, updated_at = CURRENT_TIMESTAMP WHERE telegram_id = ?",
                (name, phone, telegram_id),
            )
            return row["id"]
        cursor = conn.execute(
            "INSERT INTO clients (telegram_id, name, phone) VALUES (?, ?, ?)",
            (telegram_id, name, phone),
        )
        return cursor.lastrowid


def get_client_by_telegram(telegram_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,)).fetchone()


def create_booking(client_id: int, day: date, start_time: str, duration_min: int, total_price: int, selected_services: list[dict]) -> int:
    start_min = _time_to_minutes(start_time)
    end_time = _minutes_to_time(start_min + duration_min)
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO bookings (client_id, date, start_time, end_time, total_price) VALUES (?, ?, ?, ?, ?)",
            (client_id, _format_db_date(day), start_time, end_time, total_price),
        )
        booking_id = cursor.lastrowid
        conn.executemany(
            "INSERT INTO booking_services (booking_id, service_key, service_name, price, duration_min) VALUES (?, ?, ?, ?, ?)",
            [(booking_id, i["key"], i["name"], i["price"], i["duration_min"]) for i in selected_services],
        )
        return booking_id


def get_client_bookings(telegram_id: int, limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT b.*, GROUP_CONCAT(bs.service_name, ', ') AS services
            FROM bookings b
            JOIN clients c ON c.id = b.client_id
            JOIN booking_services bs ON bs.booking_id = b.id
            WHERE c.telegram_id = ? AND b.status = 'confirmed' AND b.date >= date('now')
            GROUP BY b.id
            ORDER BY b.date, b.start_time
            LIMIT ?
            """,
            (telegram_id, limit),
        ).fetchall()


def get_booking_by_id(booking_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT b.*, c.name, c.phone, c.telegram_id,
                   GROUP_CONCAT(bs.service_name, ', ') AS services
            FROM bookings b
            JOIN clients c ON c.id = b.client_id
            JOIN booking_services bs ON bs.booking_id = b.id
            WHERE b.id = ?
            GROUP BY b.id
            """,
            (booking_id,),
        ).fetchone()


def get_booking_service_keys(booking_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT service_key FROM booking_services WHERE booking_id = ? ORDER BY id",
            (booking_id,),
        ).fetchall()
        return [row["service_key"] for row in rows]


def cancel_booking(booking_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT b.*, c.telegram_id, c.name,
                   GROUP_CONCAT(bs.service_name, ', ') AS services
            FROM bookings b
            JOIN clients c ON c.id = b.client_id
            JOIN booking_services bs ON bs.booking_id = b.id
            WHERE b.id = ? AND b.status = 'confirmed'
            GROUP BY b.id
            """,
            (booking_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        return row


def cancel_booking_for_client(booking_id: int, telegram_id: int) -> sqlite3.Row | None:
    booking = get_booking_by_id(booking_id)
    if not booking or booking["status"] != "confirmed" or booking["telegram_id"] != telegram_id:
        return None
    return cancel_booking(booking_id)


def _replace_booking_services(conn: sqlite3.Connection, booking_id: int, service_keys: list[str]) -> tuple[int, int, list[dict]]:
    if not service_keys:
        raise ValueError("empty services")
    _, duration, items = calc_totals(service_keys)
    conn.execute("DELETE FROM booking_services WHERE booking_id = ?", (booking_id,))
    conn.executemany(
        "INSERT INTO booking_services (booking_id, service_key, service_name, price, duration_min) VALUES (?, ?, ?, ?, ?)",
        [(booking_id, i["key"], i["name"], i["price"], i["duration_min"]) for i in items],
    )
    price = sum(i["price"] for i in items)
    return price, duration, items


def update_booking_services(booking_id: int, service_keys: list[str]) -> bool:
    booking = get_booking_by_id(booking_id)
    if not booking or booking["status"] != "confirmed":
        return False
    day = date.fromisoformat(booking["date"])
    if not is_slot_available(day, booking["start_time"], calc_totals(service_keys)[1], exclude_booking_id=booking_id):
        return False
    with get_conn() as conn:
        price, duration, _ = _replace_booking_services(conn, booking_id, service_keys)
        end_time = _minutes_to_time(_time_to_minutes(booking["start_time"]) + duration)
        conn.execute(
            "UPDATE bookings SET total_price = ?, end_time = ? WHERE id = ?",
            (price, end_time, booking_id),
        )
    return True


def add_service_to_booking(booking_id: int, service_key: str) -> bool:
    keys = get_booking_service_keys(booking_id)
    if service_key in keys:
        return True
    keys.append(service_key)
    return update_booking_services(booking_id, keys)


def remove_service_from_booking(booking_id: int, service_key: str) -> bool:
    keys = get_booking_service_keys(booking_id)
    if service_key not in keys:
        return False
    if len(keys) <= 1:
        return False
    keys.remove(service_key)
    return update_booking_services(booking_id, keys)


def update_booking_time(booking_id: int, new_start_time: str) -> bool:
    booking = get_booking_by_id(booking_id)
    if not booking or booking["status"] != "confirmed":
        return False
    duration = _booking_duration_minutes(booking_id)
    day = date.fromisoformat(booking["date"])
    if not is_slot_available(day, new_start_time, duration, exclude_booking_id=booking_id):
        return False
    end_time = _minutes_to_time(_time_to_minutes(new_start_time) + duration)
    with get_conn() as conn:
        conn.execute(
            "UPDATE bookings SET start_time = ?, end_time = ?, reminder_day_sent = 0, reminder_hour_sent = 0 WHERE id = ?",
            (new_start_time, end_time, booking_id),
        )
    return True


def get_bookings_for_date(day: date) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT b.*, c.name, c.phone, c.telegram_id,
                   GROUP_CONCAT(bs.service_name, ', ') AS services
            FROM bookings b
            JOIN clients c ON c.id = b.client_id
            JOIN booking_services bs ON bs.booking_id = b.id
            WHERE b.date = ? AND b.status = 'confirmed'
            GROUP BY b.id
            ORDER BY b.start_time
            """,
            (_format_db_date(day),),
        ).fetchall()


def block_full_day(day: date, reason: str = "") -> None:
    with get_conn() as conn:
        db_date = _format_db_date(day)
        conn.execute("DELETE FROM blocked_slots WHERE date = ? AND start_time IS NULL", (db_date,))
        conn.execute(
            "INSERT INTO blocked_slots (date, start_time, end_time, reason) VALUES (?, NULL, NULL, ?)",
            (db_date, reason),
        )


def block_time_range(day: date, start_time: str, end_time: str, reason: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO blocked_slots (date, start_time, end_time, reason) VALUES (?, ?, ?, ?)",
            (_format_db_date(day), start_time, end_time, reason),
        )


def list_clients(limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT c.*, COUNT(b.id) AS bookings_count
            FROM clients c
            LEFT JOIN bookings b ON b.client_id = c.id AND b.status = 'confirmed'
            GROUP BY c.id
            ORDER BY COALESCE(c.updated_at, c.created_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def list_blocked_days(limit: int = 14) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM blocked_slots WHERE date >= date('now') ORDER BY date, start_time LIMIT ?",
            (limit,),
        ).fetchall()


def unblock_day(day: date) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM blocked_slots WHERE date = ?", (_format_db_date(day),))


def get_pending_reminders() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT b.id, b.date, b.start_time, b.reminder_day_sent, b.reminder_hour_sent,
                   c.telegram_id, GROUP_CONCAT(bs.service_name, ', ') AS services
            FROM bookings b
            JOIN clients c ON c.id = b.client_id
            JOIN booking_services bs ON bs.booking_id = b.id
            WHERE b.status = 'confirmed'
              AND datetime(b.date || ' ' || b.start_time) > datetime('now')
            GROUP BY b.id
            """
        ).fetchall()


def mark_reminder_sent(booking_id: int, kind: str) -> None:
    column = "reminder_day_sent" if kind == "day" else "reminder_hour_sent"
    with get_conn() as conn:
        conn.execute(f"UPDATE bookings SET {column} = 1 WHERE id = ?", (booking_id,))


def calc_totals(service_keys: list[str]) -> tuple[int, int, list[dict]]:
    total_price = 0
    total_duration = 0
    items: list[dict] = []
    for key in service_keys:
        service = SERVICES[key]
        total_price += service["price"]
        total_duration += service["duration_min"]
        items.append({
            "key": key,
            "name": service["name"],
            "price": service["price"],
            "duration_min": service["duration_min"],
        })
    return total_price, total_duration, items


def parse_display_date(value: str) -> date:
    return _parse_display_date(value)


def _min_service_duration() -> int:
    return min(service["duration_min"] for service in SERVICES.values())


def get_day_calendar_status(day: date) -> str:
    """free — свободен, partial — частично занят, full — полностью занят, inactive — нерабочий."""
    schedule = get_work_day(day.weekday())
    if not schedule or not schedule["is_working"]:
        return "inactive"
    if is_day_blocked(day):
        return "full"
    min_duration = _min_service_duration()
    if not get_available_times(day, min_duration):
        return "full"
    db_date = _format_db_date(day)
    with get_conn() as conn:
        has_bookings = conn.execute(
            "SELECT 1 FROM bookings WHERE date = ? AND status = 'confirmed' LIMIT 1",
            (db_date,),
        ).fetchone() is not None
        has_partial_block = conn.execute(
            "SELECT 1 FROM blocked_slots WHERE date = ? AND start_time IS NOT NULL LIMIT 1",
            (db_date,),
        ).fetchone() is not None
    if has_bookings or has_partial_block:
        return "partial"
    return "free"


def get_calendar_status_for_month(year: int, month: int) -> dict[str, str]:
    import calendar as cal_mod

    today = date.today()
    max_date = today + timedelta(days=BOOKING_DAYS_AHEAD)
    result: dict[str, str] = {}
    for week in cal_mod.Calendar(firstweekday=0).monthdatescalendar(year, month):
        for day in week:
            if day.month != month or day < today or day > max_date:
                continue
            result[_format_display_date(day)] = get_day_calendar_status(day)
    return result


def get_busy_dates_for_month(year: int, month: int) -> set[str]:
    return {
        day_str
        for day_str, status in get_calendar_status_for_month(year, month).items()
        if status in ("partial", "full")
    }
