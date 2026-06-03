import logging
import os
from datetime import date
from typing import Optional

import psycopg2
from psycopg2 import sql as pgsql
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_ALLOWED_UPDATE_FIELDS = frozenset({
    "insurance_valid_until",
    "pucc_valid_until",
    "fitness_valid_until",
    "mv_tax_valid_until",
    "permit_valid_until",
})

_VEHICLE_COLS = """
    id, nickname, registration_number, status, vehicle_class,
    fuel_type, owner_name, registration_date,
    insurance_valid_until, pucc_valid_until, fitness_valid_until,
    mv_tax_valid_until, permit_valid_until, permit_type
"""

_ORDER_BY_NEAREST = """ORDER BY LEAST(
    COALESCE(insurance_valid_until, '9999-01-01'::date),
    COALESCE(pucc_valid_until,      '9999-01-01'::date),
    COALESCE(fitness_valid_until,   '9999-01-01'::date),
    COALESCE(mv_tax_valid_until,    '9999-01-01'::date),
    COALESCE(permit_valid_until,    '9999-01-01'::date)
)"""


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URI"])


def get_vehicles_filtered(
    filter_type: str,
    value: Optional[str] = None,
    days: int = 30,
) -> list[dict]:
    if filter_type == "all":
        sql = f"SELECT {_VEHICLE_COLS} FROM vehicles ORDER BY registration_number"
        params: dict = {}
    elif filter_type == "expiring_soon":
        sql = f"""
            SELECT {_VEHICLE_COLS} FROM vehicles
            WHERE
                insurance_valid_until BETWEEN CURRENT_DATE
                    AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
                OR pucc_valid_until BETWEEN CURRENT_DATE
                    AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
                OR fitness_valid_until BETWEEN CURRENT_DATE
                    AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
                OR mv_tax_valid_until BETWEEN CURRENT_DATE
                    AND CURRENT_DATE + %(days)s * INTERVAL '1 day'
                OR (permit_valid_until IS NOT NULL
                    AND permit_valid_until BETWEEN CURRENT_DATE
                        AND CURRENT_DATE + %(days)s * INTERVAL '1 day')
            {_ORDER_BY_NEAREST}
        """
        params = {"days": days}
    elif filter_type == "expired":
        sql = f"""
            SELECT {_VEHICLE_COLS} FROM vehicles
            WHERE
                insurance_valid_until < CURRENT_DATE
                OR pucc_valid_until < CURRENT_DATE
                OR fitness_valid_until < CURRENT_DATE
                OR mv_tax_valid_until < CURRENT_DATE
                OR (permit_valid_until IS NOT NULL AND permit_valid_until < CURRENT_DATE)
            {_ORDER_BY_NEAREST}
        """
        params = {}
    elif filter_type == "by_owner":
        sql = f"""
            SELECT {_VEHICLE_COLS} FROM vehicles
            WHERE owner_name ILIKE %(value)s ORDER BY registration_number
        """
        params = {"value": f"%{value}%"}
    elif filter_type == "by_registration":
        sql = f"SELECT {_VEHICLE_COLS} FROM vehicles WHERE registration_number = %(value)s"
        params = {"value": value}
    elif filter_type == "by_nickname":
        sql = f"SELECT {_VEHICLE_COLS} FROM vehicles WHERE nickname ILIKE %(value)s"
        params = {"value": f"%{value}%"}
    else:
        raise ValueError(f"Unknown filter_type: {filter_type!r}")

    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def update_vehicle_field(registration_number: str, field: str, new_date: str) -> bool:
    if field not in _ALLOWED_UPDATE_FIELDS:
        raise ValueError(f"Field {field!r} is not updatable")
    query = pgsql.SQL(
        "UPDATE vehicles SET {col} = %(new_date)s, updated_at = now() "
        "WHERE registration_number = %(reg)s"
    ).format(col=pgsql.Identifier(field))
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(query, {"new_date": new_date, "reg": registration_number})
            return cur.rowcount > 0


def get_all_vehicles_with_expiry() -> list[dict]:
    sql = f"SELECT {_VEHICLE_COLS} FROM vehicles ORDER BY id"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]


def reminder_already_sent(
    vehicle_id: int, expiry_field: str, expiry_date: date, offset: int
) -> bool:
    sql = """
        SELECT 1 FROM reminder_log
        WHERE vehicle_id = %(vid)s
          AND expiry_field = %(field)s
          AND expiry_date = %(edate)s
          AND trigger_offset = %(offset)s
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "vid": vehicle_id, "field": expiry_field,
                "edate": expiry_date, "offset": offset,
            })
            return cur.fetchone() is not None


def log_reminder(
    vehicle_id: int, expiry_field: str, expiry_date: date, offset: int
) -> None:
    sql = """
        INSERT INTO reminder_log (vehicle_id, expiry_field, expiry_date, trigger_offset)
        VALUES (%(vid)s, %(field)s, %(edate)s, %(offset)s)
        ON CONFLICT DO NOTHING
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {
                "vid": vehicle_id, "field": expiry_field,
                "edate": expiry_date, "offset": offset,
            })


def get_chat_context(user_id: str) -> dict:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT summary FROM chat_summary WHERE user_id = %(uid)s",
                {"uid": user_id},
            )
            row = cur.fetchone()
            summary = row["summary"] if row else None
            cur.execute(
                """SELECT role, content FROM chat_messages
                   WHERE user_id = %(uid)s
                   ORDER BY created_at DESC LIMIT 10""",
                {"uid": user_id},
            )
            messages = list(reversed([dict(r) for r in cur.fetchall()]))
    return {"summary": summary, "messages": messages}


def save_turn(user_id: str, user_message: str, assistant_message: str) -> None:
    sql = (
        "INSERT INTO chat_messages (user_id, role, content) "
        "VALUES (%(uid)s, %(role)s, %(content)s)"
    )
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, [
                {"uid": user_id, "role": "user",      "content": user_message},
                {"uid": user_id, "role": "assistant", "content": assistant_message},
            ])


def get_message_count(user_id: str) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM chat_messages WHERE user_id = %(uid)s",
                {"uid": user_id},
            )
            return cur.fetchone()[0]


def summarize_if_needed(user_id: str, provider) -> None:
    if get_message_count(user_id) <= 20:
        return
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """SELECT id, role, content FROM chat_messages
                   WHERE user_id = %(uid)s ORDER BY created_at ASC LIMIT 15""",
                {"uid": user_id},
            )
            oldest = [dict(r) for r in cur.fetchall()]
            if not oldest:
                return
            cur.execute(
                "SELECT summary FROM chat_summary WHERE user_id = %(uid)s",
                {"uid": user_id},
            )
            row = cur.fetchone()
            existing = row["summary"] if row else "None"

    text = "\n".join(f"{m['role']}: {m['content']}" for m in oldest)
    new_summary = provider.generate_text(
        f"Summarise this vehicle-bot conversation into ≤150 words. "
        f"Focus on vehicles discussed, dates updated, user preferences. "
        f"Merge with existing summary.\n\nExisting: {existing}\n\nMessages:\n{text}"
    )

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO chat_summary (user_id, summary, updated_at)
                   VALUES (%(uid)s, %(s)s, now())
                   ON CONFLICT (user_id) DO UPDATE
                   SET summary = EXCLUDED.summary, updated_at = now()""",
                {"uid": user_id, "s": new_summary},
            )
            cur.execute(
                "DELETE FROM chat_messages WHERE id = ANY(%(ids)s)",
                {"ids": [m["id"] for m in oldest]},
            )
