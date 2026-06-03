# Smart Reminder System v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram+Discord bot with a Groq LLM agent for vehicle document Q&A/updates, and a separate rule-based cron engine that fires escalating expiry reminders tracked via a Postgres deduplication table.

**Architecture:** Platform-agnostic `Message` dataclass normalises Telegram/Discord input into a shared LangGraph agent (Groq + tool calls against Postgres). A standalone cron script checks each vehicle × expiry-field × milestone offset against a `reminder_log` table and fires only unsent milestones, with a 2-day catch-up window for missed runs.

**Tech Stack:** python-telegram-bot≥20, discord.py≥2, groq, langgraph, langchain-core, psycopg2-binary, python-dotenv, requests-mock, pytest

---

## File map

**Create:**
```
bot/__init__.py
bot/message.py          ← Message dataclass
bot/functions.py        ← TOOLS list, dispatch(), format_vehicles()
bot/telegram_bot.py     ← python-telegram-bot listener
bot/discord_bot.py      ← discord.py DM listener

ai/__init__.py          ← get_provider() factory
ai/base.py              ← AIProvider ABC
ai/groq_provider.py     ← Groq implementation
ai/graph.py             ← LangGraph agent loop

cron/__init__.py
cron/reminder_sweep.py  ← rule-based sweep entrypoint

db/__init__.py
db/client.py            ← all Postgres helpers
db/migrations/002_reminder_log.sql

utils/__init__.py

tests/__init__.py
tests/test_db.py
tests/test_functions.py
tests/test_cron.py
tests/test_graph.py

Dockerfile
```

**Modify:**
```
main.py           ← rewrite: Telegram main thread + Discord daemon thread
requirements.txt  ← add new deps
utils/notify.py   ← add send_discord(), update notify() signature
.env.example      ← add new vars
```

**Delete:**
```
utils/db.py        ← replaced by db/client.py
utils/telegram_.py ← replaced by utils/notify.py
```

---

## Task 1: Project skeleton

**Files:** `requirements.txt`, `utils/__init__.py`, `bot/__init__.py`, `ai/__init__.py`, `cron/__init__.py`, `db/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: Delete old files**

```bash
cd /home/thomas/repos/Smart_Reminder_System
rm utils/db.py utils/telegram_.py
```

- [ ] **Step 2: Create package directories and empty `__init__.py` files**

```bash
mkdir -p bot ai cron db/migrations tests
touch bot/__init__.py ai/__init__.py cron/__init__.py db/__init__.py tests/__init__.py utils/__init__.py
```

- [ ] **Step 3: Rewrite `requirements.txt`**

```
psycopg2-binary
requests
python-telegram-bot>=20.0
discord.py>=2.0
groq
langgraph
langchain-core
python-dotenv
pytest
pytest-mock
requests-mock
```

- [ ] **Step 4: Update `.env.example`**

```
# Postgres — use claude_rw role
DATABASE_URI=postgresql://claude_rw:password@localhost:5432/homelab

# Telegram bot (from @BotFather)
TELEGRAM_BOT_TOKEN=
# Your Telegram chat ID (from @userinfobot) — used by cron alerts
TELEGRAM_CHAT_ID=

# Discord bot (optional)
DISCORD_BOT_TOKEN=
# Discord channel ID for cron alerts (optional)
DISCORD_CHANNEL_ID=

# Groq API key (https://console.groq.com)
GROQ_API_KEY=
# AI provider: groq (only option for now)
AI_PROVIDER=groq

# Cron reminder delivery
CRON_NOTIFY_PLATFORM=telegram
CRON_NOTIFY_CHAT_ID=   # leave blank to use TELEGRAM_CHAT_ID
```

- [ ] **Step 5: Install deps**

```bash
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: restructure project skeleton for v2"
```

---

## Task 2: Bot Message dataclass

**Files:** Create `bot/message.py`, create `tests/test_functions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_functions.py
import pytest

def test_message_dataclass():
    from bot.message import Message
    msg = Message(platform="telegram", user_id="telegram:123", chat_id="456", text="hello")
    assert msg.platform == "telegram"
    assert msg.user_id == "telegram:123"
    assert msg.chat_id == "456"
    assert msg.text == "hello"
```

- [ ] **Step 2: Run test — expect failure**

```bash
pytest tests/test_functions.py::test_message_dataclass -v
```

Expected: `ModuleNotFoundError: No module named 'bot.message'`

- [ ] **Step 3: Create `bot/message.py`**

```python
from dataclasses import dataclass


@dataclass
class Message:
    platform: str   # "telegram" | "discord"
    user_id: str    # "{platform}:{id}", e.g. "telegram:123456"
    chat_id: str    # platform channel/chat ID used to send replies
    text: str
```

- [ ] **Step 4: Run test — expect pass**

```bash
pytest tests/test_functions.py::test_message_dataclass -v
```

Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/message.py tests/test_functions.py
git commit -m "feat: platform-agnostic Message dataclass"
```

---

## Task 3: DB migration

**Files:** Create `db/migrations/002_reminder_log.sql`

Three tables:
- `reminder_log` — deduplicates cron milestones. UNIQUE on `(vehicle_id, expiry_field, expiry_date, trigger_offset)` means renewing a document (new expiry_date) resets the cycle automatically.
- `chat_messages` — per-user conversation history. `user_id` format: `"telegram:123"` or `"discord:456"`.
- `chat_summary` — compressed memory written when message count exceeds 20.

- [ ] **Step 1: Write migration file**

```sql
-- db/migrations/002_reminder_log.sql

CREATE TABLE IF NOT EXISTS reminder_log (
    id             BIGSERIAL PRIMARY KEY,
    vehicle_id     BIGINT NOT NULL REFERENCES vehicles(id),
    expiry_field   TEXT NOT NULL,
    expiry_date    DATE NOT NULL,
    trigger_offset INT NOT NULL,   -- negative = days before expiry, positive = days after
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (vehicle_id, expiry_field, expiry_date, trigger_offset)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         BIGSERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_user_created
    ON chat_messages (user_id, created_at);

CREATE TABLE IF NOT EXISTS chat_summary (
    user_id    TEXT PRIMARY KEY,
    summary    TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: Run migration against live DB**

```bash
docker exec -i homelab-postgres psql -U homelab -d homelab \
  < db/migrations/002_reminder_log.sql
```

Expected: `CREATE TABLE`, `CREATE INDEX`, `CREATE TABLE` — no errors.

- [ ] **Step 3: Verify tables exist**

```bash
docker exec homelab-postgres psql -U homelab -d homelab \
  -c "\dt reminder_log chat_messages chat_summary"
```

Expected: three rows in the table list.

- [ ] **Step 4: Commit**

```bash
git add db/migrations/002_reminder_log.sql
git commit -m "feat: reminder_log and chat memory migrations"
```

---

## Task 4: DB client — vehicle queries

**Files:** Create `db/client.py`, create `tests/test_db.py`

These are integration tests against the live DB. Run with `pytest -m integration`. The seeded data has 7 vehicles (Thomas J Varghese owns Honda Highness + Activa 6G; Varghese Joseph owns Vespa + Enfield Bullet + Toyota Etios; Joseph C Varghese owns Escorts; Suzuki Fiero owner masked). Toyota Etios has `status = 'Fitness Expired'`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db.py
import os
import pytest
import psycopg2
from datetime import date, timedelta

pytestmark = pytest.mark.integration


def test_get_vehicles_all():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("all")
    assert len(vehicles) == 7
    assert all("registration_number" in v for v in vehicles)


def test_get_vehicles_by_owner():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("by_owner", value="Thomas")
    assert len(vehicles) == 2
    assert all("Thomas" in v["owner_name"] for v in vehicles)


def test_get_vehicles_by_registration():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("by_registration", value="KL04AS1371")
    assert len(vehicles) == 1
    assert vehicles[0]["nickname"] == "Honda Highness"


def test_get_vehicles_by_nickname():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("by_nickname", value="activa")
    assert len(vehicles) == 1
    assert vehicles[0]["registration_number"] == "KL04AQ2807"


def test_get_vehicles_expiring_soon():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("expiring_soon", days=365)
    assert len(vehicles) > 0


def test_get_vehicles_expired():
    from db.client import get_vehicles_filtered
    vehicles = get_vehicles_filtered("expired")
    regs = [v["registration_number"] for v in vehicles]
    assert "KL04AB6528" in regs  # Toyota Etios has expired fitness


def test_get_vehicles_unknown_filter():
    from db.client import get_vehicles_filtered
    with pytest.raises(ValueError, match="Unknown filter_type"):
        get_vehicles_filtered("bad_filter")


def test_update_vehicle_field_rejects_bad_field():
    from db.client import update_vehicle_field
    with pytest.raises(ValueError, match="not updatable"):
        update_vehicle_field("KL04AS1371", "owner_name", "2027-01-01")
```

- [ ] **Step 2: Run tests — expect failure**

```bash
pytest tests/test_db.py -m integration -v
```

Expected: `ModuleNotFoundError: No module named 'db.client'`

- [ ] **Step 3: Create `db/client.py` — vehicle section**

```python
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
    """Update one expiry field. Returns True if a row was matched."""
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
    """Return all vehicles — used by the cron sweep."""
    sql = f"SELECT {_VEHICLE_COLS} FROM vehicles ORDER BY id"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_db.py -m integration -v
```

Expected: all 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: db client — vehicle query and update helpers"
```

---

## Task 5: DB client — reminder log

**Files:** Extend `db/client.py`, extend `tests/test_db.py`

- [ ] **Step 1: Append failing tests to `tests/test_db.py`**

```python
def test_reminder_log_round_trip():
    from db.client import reminder_already_sent, log_reminder
    vid, field, expiry, offset = 1, "insurance_valid_until", date(2099, 1, 1), -999
    assert not reminder_already_sent(vid, field, expiry, offset)
    log_reminder(vid, field, expiry, offset)
    assert reminder_already_sent(vid, field, expiry, offset)
    conn = psycopg2.connect(os.environ["DATABASE_URI"])
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM reminder_log WHERE vehicle_id=%s AND expiry_date=%s AND trigger_offset=%s",
                (vid, expiry, offset),
            )
    conn.close()


def test_reminder_log_idempotent():
    from db.client import log_reminder, reminder_already_sent
    vid, field, expiry, offset = 1, "pucc_valid_until", date(2098, 6, 1), -888
    log_reminder(vid, field, expiry, offset)
    log_reminder(vid, field, expiry, offset)  # must not raise
    assert reminder_already_sent(vid, field, expiry, offset)
    conn = psycopg2.connect(os.environ["DATABASE_URI"])
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM reminder_log WHERE vehicle_id=%s AND expiry_date=%s AND trigger_offset=%s",
                (vid, expiry, offset),
            )
    conn.close()
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_db.py::test_reminder_log_round_trip -m integration -v
```

Expected: `AttributeError: module 'db.client' has no attribute 'reminder_already_sent'`

- [ ] **Step 3: Append to `db/client.py`**

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_db.py -m integration -v
```

Expected: all 10 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: db client — reminder_log helpers"
```

---

## Task 6: DB client — chat memory

**Files:** Extend `db/client.py`, extend `tests/test_db.py`

- [ ] **Step 1: Append failing tests to `tests/test_db.py`**

```python
def _clean_chat(user_id: str) -> None:
    conn = psycopg2.connect(os.environ["DATABASE_URI"])
    with conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chat_messages WHERE user_id=%s", (user_id,))
            cur.execute("DELETE FROM chat_summary WHERE user_id=%s", (user_id,))
    conn.close()


def test_chat_context_empty_for_new_user():
    from db.client import get_chat_context
    uid = "test:unit_empty"
    _clean_chat(uid)
    ctx = get_chat_context(uid)
    assert ctx["summary"] is None
    assert ctx["messages"] == []


def test_chat_save_and_retrieve():
    from db.client import get_chat_context, save_turn, get_message_count
    uid = "test:unit_save"
    _clean_chat(uid)
    save_turn(uid, "What expires soon?", "Your PUCC is due in 7 days.")
    assert get_message_count(uid) == 2
    ctx = get_chat_context(uid)
    assert len(ctx["messages"]) == 2
    assert ctx["messages"][0]["role"] == "user"
    assert ctx["messages"][1]["role"] == "assistant"
    _clean_chat(uid)
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_db.py::test_chat_context_empty_for_new_user -m integration -v
```

Expected: `AttributeError: module 'db.client' has no attribute 'get_chat_context'`

- [ ] **Step 3: Append to `db/client.py`**

```python
def get_chat_context(user_id: str) -> dict:
    """Return {'summary': str|None, 'messages': list[dict]} for a user."""
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
    """Summarise oldest 15 messages into chat_summary when total > 20."""
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
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_db.py -m integration -v
```

Expected: all 12 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db.py
git commit -m "feat: db client — chat memory helpers"
```

---

## Task 7: Notify util

**Files:** Rewrite `utils/notify.py`, extend `tests/test_functions.py`

- [ ] **Step 1: Append failing tests to `tests/test_functions.py`**

```python
def test_send_telegram_posts_to_correct_url(requests_mock, monkeypatch):
    from utils.notify import send_telegram
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test_token")
    requests_mock.post(
        "https://api.telegram.org/bottest_token/sendMessage", json={"ok": True}
    )
    send_telegram("hello", "12345")
    assert requests_mock.called
    body = requests_mock.last_request.json()
    assert body["chat_id"] == "12345"
    assert body["text"] == "hello"


def test_send_discord_posts_to_correct_url(requests_mock, monkeypatch):
    from utils.notify import send_discord
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "disc_token")
    requests_mock.post(
        "https://discord.com/api/v10/channels/99/messages", json={"id": "1"}
    )
    send_discord("hi discord", "99")
    assert requests_mock.called
    assert requests_mock.last_request.json()["content"] == "hi discord"


def test_notify_defaults_to_telegram(requests_mock, monkeypatch):
    from utils.notify import notify
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "777")
    requests_mock.post(
        "https://api.telegram.org/bottok/sendMessage", json={"ok": True}
    )
    notify("test message")
    assert requests_mock.called


def test_notify_unknown_platform():
    from utils.notify import notify
    with pytest.raises(ValueError, match="Unknown platform"):
        notify("msg", platform="carrier_pigeon")
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_functions.py::test_send_telegram_posts_to_correct_url -v
```

Expected: fails (old `notify.py` has different signature).

- [ ] **Step 3: Rewrite `utils/notify.py`**

```python
import os
import requests


def send_telegram(text: str, chat_id: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    resp.raise_for_status()


def send_discord(text: str, channel_id: str) -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    resp = requests.post(
        url, json={"content": text[:2000]}, headers=headers, timeout=10
    )
    resp.raise_for_status()


def notify(text: str, platform: str = "telegram", chat_id: str | None = None) -> None:
    """Send to a configured channel. Used by cron reminders."""
    if platform == "telegram":
        send_telegram(text, chat_id or os.environ["TELEGRAM_CHAT_ID"])
    elif platform == "discord":
        send_discord(text, chat_id or os.environ["DISCORD_CHANNEL_ID"])
    else:
        raise ValueError(f"Unknown platform: {platform!r}")
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_functions.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add utils/notify.py tests/test_functions.py
git commit -m "feat: notify util — Telegram + Discord send functions"
```

---

## Task 8: AI provider

**Files:** Create `ai/base.py`, `ai/groq_provider.py`, `ai/__init__.py`, create `tests/test_graph.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_graph.py
import pytest
from unittest.mock import MagicMock, patch


def test_ai_provider_abc_cannot_be_instantiated():
    from ai.base import AIProvider
    with pytest.raises(TypeError):
        AIProvider()


def test_groq_provider_generate_text(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake_key")
    from ai.groq_provider import GroqProvider
    provider = GroqProvider.__new__(GroqProvider)
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = "hello"
    provider._client = mock_client
    assert provider.generate_text("say hello") == "hello"


def test_groq_provider_returns_text(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake_key")
    from ai.groq_provider import GroqProvider
    provider = GroqProvider.__new__(GroqProvider)
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Insurance expires in 30 days."
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_client.chat.completions.create.return_value = mock_response
    provider._client = mock_client
    result = provider.chat_with_tools([{"role": "user", "content": "test"}], [])
    assert result["text"] == "Insurance expires in 30 days."
    assert result["usage"]["input_tokens"] == 10


def test_groq_provider_returns_tool_calls(monkeypatch):
    import json
    monkeypatch.setenv("GROQ_API_KEY", "fake_key")
    from ai.groq_provider import GroqProvider
    provider = GroqProvider.__new__(GroqProvider)
    mock_client = MagicMock()
    mock_tc = MagicMock()
    mock_tc.function.name = "query_vehicles"
    mock_tc.function.arguments = json.dumps({"filter": "all"})
    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = [mock_tc]
    mock_response.usage.prompt_tokens = 5
    mock_response.usage.completion_tokens = 8
    mock_client.chat.completions.create.return_value = mock_response
    provider._client = mock_client
    result = provider.chat_with_tools([{"role": "user", "content": "list all"}], [])
    assert "tool_calls" in result
    assert result["tool_calls"][0] == {"name": "query_vehicles", "arguments": {"filter": "all"}}


def test_get_provider_returns_groq(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "fake_key")
    from ai import get_provider
    from ai.groq_provider import GroqProvider
    assert isinstance(get_provider(), GroqProvider)


def test_get_provider_unknown_raises(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gpt99")
    monkeypatch.setenv("GROQ_API_KEY", "fake_key")
    from ai import get_provider
    with pytest.raises(ValueError, match="Unknown AI_PROVIDER"):
        get_provider()
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_graph.py::test_ai_provider_abc_cannot_be_instantiated -v
```

Expected: `ModuleNotFoundError: No module named 'ai.base'`

- [ ] **Step 3: Create `ai/base.py`**

```python
from abc import ABC, abstractmethod


class AIProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        """Generate plain text for a prompt (used for summarisation)."""

    @abstractmethod
    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        """
        Send messages with optional tool definitions.
        Returns one of:
          {"text": "...", "usage": {"input_tokens": int, "output_tokens": int}}
          {"tool_calls": [{"name": str, "arguments": dict}], "usage": {...}}
        """
```

- [ ] **Step 4: Create `ai/groq_provider.py`**

```python
import json
import os

from groq import Groq

from ai.base import AIProvider

_MODEL = "llama-3.3-70b-versatile"


class GroqProvider(AIProvider):
    def __init__(self):
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate_text(self, prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> dict:
        response = self._client.chat.completions.create(
            model=_MODEL,
            messages=messages,
            tools=tools if tools else None,
        )
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        msg = response.choices[0].message
        if msg.tool_calls:
            return {
                "tool_calls": [
                    {
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    }
                    for tc in msg.tool_calls
                ],
                "usage": usage,
            }
        return {"text": msg.content or "", "usage": usage}
```

- [ ] **Step 5: Create `ai/__init__.py`**

```python
import os

from ai.base import AIProvider


def get_provider() -> AIProvider:
    name = os.environ.get("AI_PROVIDER", "groq").lower()
    if name == "groq":
        from ai.groq_provider import GroqProvider
        return GroqProvider()
    raise ValueError(f"Unknown AI_PROVIDER: {name!r}")
```

- [ ] **Step 6: Run tests — expect pass**

```bash
pytest tests/test_graph.py -v
```

Expected: all 6 tests PASSED.

- [ ] **Step 7: Commit**

```bash
git add ai/ tests/test_graph.py
git commit -m "feat: AIProvider ABC + Groq implementation"
```

---

## Task 9: Bot tools and vehicle formatting

**Files:** Create `bot/functions.py`, extend `tests/test_functions.py`

- [ ] **Step 1: Append failing tests to `tests/test_functions.py`**

```python
def test_format_vehicles_empty():
    from bot.functions import format_vehicles
    assert format_vehicles([]) == "No vehicles found."


def test_format_vehicles_countdown():
    from datetime import date, timedelta
    from bot.functions import format_vehicles
    future = date.today() + timedelta(days=10)
    result = format_vehicles([{
        "nickname": "Test Bike", "registration_number": "KL99ZZ0001",
        "owner_name": "Test User", "insurance_valid_until": future,
        "pucc_valid_until": None, "fitness_valid_until": None,
        "mv_tax_valid_until": None, "permit_valid_until": None,
    }])
    assert "Test Bike" in result
    assert "in 10d" in result


def test_format_vehicles_expired():
    from datetime import date, timedelta
    from bot.functions import format_vehicles
    past = date.today() - timedelta(days=5)
    result = format_vehicles([{
        "nickname": None, "registration_number": "KL00AA0000",
        "owner_name": None, "insurance_valid_until": past,
        "pucc_valid_until": None, "fitness_valid_until": None,
        "mv_tax_valid_until": None, "permit_valid_until": None,
    }])
    assert "EXPIRED 5d ago" in result


def test_dispatch_unknown_tool():
    from bot.functions import dispatch
    assert "Unknown tool" in dispatch("no_such_tool", {}, "telegram:1")


def test_tools_list_has_required_entries():
    from bot.functions import TOOLS
    names = [t["function"]["name"] for t in TOOLS]
    assert "query_vehicles" in names
    assert "update_vehicle_expiry" in names
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_functions.py::test_format_vehicles_empty -v
```

Expected: `ModuleNotFoundError: No module named 'bot.functions'`

- [ ] **Step 3: Create `bot/functions.py`**

```python
from datetime import date
from typing import Optional

from db import client as db

_FIELD_LABELS: dict[str, str] = {
    "insurance_valid_until": "Insurance",
    "pucc_valid_until":      "Pollution (PUCC)",
    "fitness_valid_until":   "Fitness / RC validity",
    "mv_tax_valid_until":    "MV Tax",
    "permit_valid_until":    "Permit",
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_vehicles",
            "description": (
                "Query vehicles from the database. Use for questions about "
                "expiry dates, document status, owners, or vehicle details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": [
                            "all", "expiring_soon", "expired",
                            "by_owner", "by_registration", "by_nickname",
                        ],
                        "description": "Filter type to apply",
                    },
                    "value": {
                        "type": "string",
                        "description": "Filter value for by_owner/by_registration/by_nickname",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Lookahead days for expiring_soon (default 30)",
                    },
                },
                "required": ["filter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_vehicle_expiry",
            "description": (
                "Update an expiry date on a vehicle. "
                "STRICT RULE: call query_vehicles first, show old → new to user, "
                "ask 'Confirm?', and only call this after explicit user confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "registration_number": {
                        "type": "string",
                        "description": "Vehicle registration number, e.g. KL04AS1371",
                    },
                    "field": {
                        "type": "string",
                        "enum": list(_FIELD_LABELS.keys()),
                        "description": "The expiry field to update",
                    },
                    "new_date": {
                        "type": "string",
                        "description": "New expiry date in YYYY-MM-DD format",
                    },
                },
                "required": ["registration_number", "field", "new_date"],
            },
        },
    },
]


def dispatch(name: str, arguments: dict, user_id: str) -> str:
    if name == "query_vehicles":
        return _query_vehicles(arguments)
    if name == "update_vehicle_expiry":
        return _update_vehicle_expiry(arguments)
    return f"Unknown tool: {name}"


def _query_vehicles(args: dict) -> str:
    vehicles = db.get_vehicles_filtered(
        filter_type=args["filter"],
        value=args.get("value"),
        days=args.get("days", 30),
    )
    return format_vehicles(vehicles)


def _update_vehicle_expiry(args: dict) -> str:
    success = db.update_vehicle_field(
        registration_number=args["registration_number"],
        field=args["field"],
        new_date=args["new_date"],
    )
    if success:
        label = _FIELD_LABELS.get(args["field"], args["field"])
        return (
            f"Updated {label} for {args['registration_number']} to {args['new_date']}."
        )
    return f"Vehicle {args['registration_number']} not found."


def _fmt_expiry(val: Optional[date], today: date) -> str:
    if val is None:
        return "N/A"
    remaining = (val - today).days
    if remaining < 0:
        return f"{val} (EXPIRED {-remaining}d ago)"
    if remaining == 0:
        return f"{val} (expires TODAY)"
    return f"{val} (in {remaining}d)"


def format_vehicles(vehicles: list[dict]) -> str:
    if not vehicles:
        return "No vehicles found."
    today = date.today()
    parts = []
    for v in vehicles:
        name  = v.get("nickname") or v["registration_number"]
        owner = v.get("owner_name") or "Unknown"
        lines = [f"{name} ({v['registration_number']}) — {owner}"]
        for field, label in _FIELD_LABELS.items():
            val = v.get(field)
            if val is not None:
                lines.append(f"  {label}: {_fmt_expiry(val, today)}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_functions.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Commit**

```bash
git add bot/functions.py tests/test_functions.py
git commit -m "feat: bot tools — TOOLS list, dispatch, format_vehicles"
```

---

## Task 10: LangGraph agent

**Files:** Create `ai/graph.py`, extend `tests/test_graph.py`

- [ ] **Step 1: Append failing tests to `tests/test_graph.py`**

```python
def _make_msg(text: str = "test"):
    from bot.message import Message
    return Message(platform="telegram", user_id="telegram:999", chat_id="123", text=text)


@patch("ai.graph.get_provider")
@patch("ai.graph.get_chat_context", return_value={"summary": None, "messages": []})
@patch("ai.graph.save_turn")
@patch("ai.graph.summarize_if_needed")
def test_run_graph_plain_response(mock_sum, mock_save, mock_ctx, mock_prov):
    from ai.graph import run_graph
    provider = MagicMock()
    provider.chat_with_tools.return_value = {"text": "Insurance expires in 200 days."}
    mock_prov.return_value = provider
    result = run_graph(_make_msg("When does Honda insurance expire?"))
    assert isinstance(result, str) and len(result) > 0
    mock_save.assert_called_once()


@patch("ai.graph.get_provider")
@patch("ai.graph.get_chat_context", return_value={"summary": None, "messages": []})
@patch("ai.graph.save_turn")
@patch("ai.graph.summarize_if_needed")
@patch("ai.graph.dispatch", return_value="Honda Highness — Insurance: 2027-02-18 (in 260d)")
def test_run_graph_executes_tool(mock_dispatch, mock_sum, mock_save, mock_ctx, mock_prov):
    from ai.graph import run_graph
    provider = MagicMock()
    provider.chat_with_tools.side_effect = [
        {"tool_calls": [{"name": "query_vehicles", "arguments": {"filter": "by_nickname", "value": "Honda"}}]},
        {"text": "Honda Highness insurance expires 2027-02-18."},
    ]
    mock_prov.return_value = provider
    result = run_graph(_make_msg("Show Honda details"))
    mock_dispatch.assert_called_once_with(
        "query_vehicles", {"filter": "by_nickname", "value": "Honda"}, "telegram:999"
    )
    assert result == "Honda Highness insurance expires 2027-02-18."


@patch("ai.graph.get_provider")
@patch("ai.graph.get_chat_context", return_value={"summary": "User has Honda.", "messages": []})
@patch("ai.graph.save_turn")
@patch("ai.graph.summarize_if_needed")
def test_run_graph_injects_summary(mock_sum, mock_save, mock_ctx, mock_prov):
    from ai.graph import run_graph
    provider = MagicMock()
    provider.chat_with_tools.return_value = {"text": "ok"}
    mock_prov.return_value = provider
    run_graph(_make_msg("list all"))
    system_msg = provider.chat_with_tools.call_args[0][0][0]["content"]
    assert "Honda" in system_msg
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_graph.py::test_run_graph_plain_response -v
```

Expected: `ModuleNotFoundError: No module named 'ai.graph'`

- [ ] **Step 3: Create `ai/graph.py`**

```python
import logging
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph

from ai import get_provider
from bot.functions import TOOLS, dispatch
from bot.message import Message
from db.client import get_chat_context, save_turn, summarize_if_needed

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5

_SYSTEM_PROMPT = """\
You are VehicleBot, a smart assistant for managing family vehicle documents in Kerala, India.

The database tracks these expiry dates per vehicle:
- Insurance           (insurance_valid_until)
- Pollution / PUCC    (pucc_valid_until)
- Fitness / RC        (fitness_valid_until)
- MV Tax              (mv_tax_valid_until)
- Permit              (permit_valid_until) — commercial vehicles only

Family owners: Thomas J Varghese, Varghese Joseph, Joseph C Varghese.
Always show dates with days remaining, e.g. "2027-02-18 (in 260 days)".

UPDATE RULES (strict):
1. Call query_vehicles to fetch the current value first.
2. Show the user: "I'll update [vehicle] [document] from [old] → [new]. Confirm?"
3. Wait for explicit confirmation (yes / confirm / ok / proceed).
4. Only then call update_vehicle_expiry.
Never skip the confirmation step.\
"""


class GraphState(TypedDict):
    user_id: str
    chat_id: str
    platform: str
    user_message: str
    messages: list[dict]
    tool_iteration: int
    final_reply: str
    pending_tool_calls: list[dict]


def load_memory(state: GraphState) -> GraphState:
    context = get_chat_context(state["user_id"])
    system = _SYSTEM_PROMPT
    if context["summary"]:
        system += f"\n\nConversation summary:\n{context['summary']}"
    history = [{"role": m["role"], "content": m["content"]} for m in context["messages"]]
    messages = (
        [{"role": "system", "content": system}]
        + history
        + [{"role": "user", "content": state["user_message"]}]
    )
    return {**state, "messages": messages}


def agent(state: GraphState) -> GraphState:
    provider = get_provider()
    has_tool_results = any(
        m.get("role") == "user" and m.get("content", "").startswith("Tool results:")
        for m in state["messages"]
    )
    tools = [] if has_tool_results else TOOLS
    result = provider.chat_with_tools(state["messages"], tools)
    if "tool_calls" in result:
        return {**state, "pending_tool_calls": result["tool_calls"], "final_reply": ""}
    return {
        **state,
        "final_reply": result.get("text", "I'm not sure how to help with that."),
        "pending_tool_calls": [],
    }


def execute_tools(state: GraphState) -> GraphState:
    if state["tool_iteration"] >= MAX_TOOL_ITERATIONS:
        return {
            **state,
            "final_reply": "Too many tool calls — please try again.",
            "pending_tool_calls": [],
        }
    results = []
    for tc in state["pending_tool_calls"]:
        try:
            r = dispatch(tc["name"], tc.get("arguments") or {}, state["user_id"])
        except Exception as exc:
            r = f"Error in {tc['name']}: {exc}"
        results.append(r)
    new_messages = state["messages"] + [
        {"role": "user", "content": f"Tool results: {'; '.join(results)}"}
    ]
    return {
        **state,
        "messages": new_messages,
        "tool_iteration": state["tool_iteration"] + 1,
        "pending_tool_calls": [],
    }


def save_memory(state: GraphState) -> GraphState:
    try:
        save_turn(state["user_id"], state["user_message"], state["final_reply"])
        summarize_if_needed(state["user_id"], get_provider())
    except Exception as exc:
        logger.warning("Memory save failed: %s", exc)
    return state


def _route_agent(state: GraphState) -> Literal["execute_tools", "save_memory"]:
    return "execute_tools" if state.get("pending_tool_calls") else "save_memory"


def _route_tools(state: GraphState) -> Literal["agent", "save_memory"]:
    return "save_memory" if state.get("final_reply") else "agent"


def _build_graph():
    g = StateGraph(GraphState)
    g.add_node("load_memory", load_memory)
    g.add_node("agent", agent)
    g.add_node("execute_tools", execute_tools)
    g.add_node("save_memory", save_memory)
    g.set_entry_point("load_memory")
    g.add_edge("load_memory", "agent")
    g.add_conditional_edges("agent", _route_agent)
    g.add_conditional_edges("execute_tools", _route_tools)
    g.add_edge("save_memory", END)
    return g.compile()


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


def run_graph(msg: Message) -> str:
    state: GraphState = {
        "user_id": msg.user_id,
        "chat_id": msg.chat_id,
        "platform": msg.platform,
        "user_message": msg.text,
        "messages": [],
        "tool_iteration": 0,
        "final_reply": "",
        "pending_tool_calls": [],
    }
    return _get_graph().invoke(state)["final_reply"]
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_graph.py -v
```

Expected: all 9 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add ai/graph.py tests/test_graph.py
git commit -m "feat: LangGraph agent loop with memory and tool routing"
```

---

## Task 11: Cron sweep engine

**Files:** Create `cron/reminder_sweep.py`, create `tests/test_cron.py`

- [ ] **Step 1: Create `tests/test_cron.py`**

```python
# tests/test_cron.py
import pytest
from datetime import date, timedelta
from unittest.mock import patch


def test_build_message_days_before():
    from cron.reminder_sweep import _build_message
    v = {"nickname": "Honda Highness", "registration_number": "KL04AS1371", "owner_name": "Thomas J Varghese"}
    expiry = date.today() + timedelta(days=3)
    msg = _build_message(v, "Insurance", expiry, 3)
    assert "Honda Highness" in msg
    assert "in 3 day(s)" in msg


def test_build_message_expired():
    from cron.reminder_sweep import _build_message
    v = {"nickname": "Toyota Etios", "registration_number": "KL04AB6528", "owner_name": "Varghese Joseph"}
    msg = _build_message(v, "Fitness / RC validity", date.today() - timedelta(days=10), -10)
    assert "EXPIRED 10 day(s) ago" in msg


def test_build_message_today():
    from cron.reminder_sweep import _build_message
    v = {"nickname": "Vespa", "registration_number": "KL04AF2342", "owner_name": "Varghese Joseph"}
    msg = _build_message(v, "Insurance", date.today(), 0)
    assert "expires TODAY" in msg


def test_all_offsets_coverage():
    from cron.reminder_sweep import ALL_OFFSETS
    for expected in [-30, -14, -7, -3, -1, 0, 1, 3, 7, 15, 30]:
        assert expected in ALL_OFFSETS


@patch("cron.reminder_sweep.notify")
@patch("cron.reminder_sweep.db.log_reminder")
@patch("cron.reminder_sweep.db.reminder_already_sent", return_value=False)
@patch("cron.reminder_sweep.db.get_all_vehicles_with_expiry")
def test_sweep_fires_at_trigger_day(mock_get, mock_sent, mock_log, mock_notify, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    today = date.today()
    expiry = today + timedelta(days=7)
    mock_get.return_value = [{
        "id": 1, "nickname": "Honda Highness", "registration_number": "KL04AS1371",
        "owner_name": "Thomas J Varghese",
        "insurance_valid_until": expiry, "pucc_valid_until": None,
        "fitness_valid_until": None, "mv_tax_valid_until": None, "permit_valid_until": None,
    }]
    from cron.reminder_sweep import sweep
    count = sweep()
    assert count == 1
    mock_notify.assert_called_once()
    mock_log.assert_called_once_with(1, "insurance_valid_until", expiry, -7)


@patch("cron.reminder_sweep.notify")
@patch("cron.reminder_sweep.db.reminder_already_sent", return_value=True)
@patch("cron.reminder_sweep.db.get_all_vehicles_with_expiry")
def test_sweep_skips_already_sent(mock_get, mock_sent, mock_notify, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    today = date.today()
    mock_get.return_value = [{
        "id": 1, "nickname": "Vespa", "registration_number": "KL04AF2342",
        "owner_name": "X", "insurance_valid_until": today + timedelta(days=7),
        "pucc_valid_until": None, "fitness_valid_until": None,
        "mv_tax_valid_until": None, "permit_valid_until": None,
    }]
    from cron.reminder_sweep import sweep
    assert sweep() == 0
    mock_notify.assert_not_called()


@patch("cron.reminder_sweep.notify")
@patch("cron.reminder_sweep.db.log_reminder")
@patch("cron.reminder_sweep.db.reminder_already_sent", return_value=False)
@patch("cron.reminder_sweep.db.get_all_vehicles_with_expiry")
def test_sweep_catches_up_missed_trigger(mock_get, mock_sent, mock_log, mock_notify, monkeypatch):
    """Trigger was yesterday (day 6 remaining), still within 2-day catch-up window."""
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    today = date.today()
    expiry = today + timedelta(days=6)
    mock_get.return_value = [{
        "id": 1, "nickname": "Vespa", "registration_number": "KL04AF2342",
        "owner_name": "X", "insurance_valid_until": expiry,
        "pucc_valid_until": None, "fitness_valid_until": None,
        "mv_tax_valid_until": None, "permit_valid_until": None,
    }]
    from cron.reminder_sweep import sweep
    assert sweep() == 1
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_cron.py::test_build_message_days_before -v
```

Expected: `ModuleNotFoundError: No module named 'cron.reminder_sweep'`

- [ ] **Step 3: Create `cron/reminder_sweep.py`**

```python
import logging
import os
from datetime import date, timedelta

from dotenv import load_dotenv

from db import client as db
from utils.notify import notify

logger = logging.getLogger(__name__)

PRE_OFFSETS  = [-30, -14, -7, -3, -1, 0]
POST_OFFSETS = [1, 3, 7, 15, 30]
ALL_OFFSETS  = PRE_OFFSETS + POST_OFFSETS
CATCH_UP_DAYS = 2

_FIELD_LABELS: dict[str, str] = {
    "insurance_valid_until": "Insurance",
    "pucc_valid_until":      "Pollution (PUCC)",
    "fitness_valid_until":   "Fitness / RC validity",
    "mv_tax_valid_until":    "MV Tax",
    "permit_valid_until":    "Permit",
}


def _build_message(vehicle: dict, label: str, expiry: date, remaining: int) -> str:
    name  = vehicle.get("nickname") or vehicle["registration_number"]
    owner = vehicle.get("owner_name") or "Unknown"
    if remaining < 0:
        status = f"EXPIRED {-remaining} day(s) ago"
    elif remaining == 0:
        status = "expires TODAY"
    else:
        status = f"in {remaining} day(s)"
    return (
        f"<b>Vehicle Reminder</b>\n"
        f"{name} ({vehicle['registration_number']}) — {owner}\n"
        f"{label}: {expiry}  ({status})"
    )


def sweep() -> int:
    today    = date.today()
    vehicles = db.get_all_vehicles_with_expiry()
    platform = os.environ.get("CRON_NOTIFY_PLATFORM", "telegram")
    chat_id  = os.environ.get("CRON_NOTIFY_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
    sent = 0

    for v in vehicles:
        for field, label in _FIELD_LABELS.items():
            expiry: date | None = v.get(field)
            if expiry is None:
                continue
            for offset in ALL_OFFSETS:
                trigger_date = expiry + timedelta(days=offset)
                in_window = trigger_date <= today <= trigger_date + timedelta(days=CATCH_UP_DAYS)
                if not in_window:
                    continue
                if db.reminder_already_sent(v["id"], field, expiry, offset):
                    continue
                remaining = (expiry - today).days
                notify(_build_message(v, label, expiry, remaining), platform=platform, chat_id=chat_id)
                db.log_reminder(v["id"], field, expiry, offset)
                sent += 1
                logger.info("Sent: %s %s offset=%d", v["registration_number"], field, offset)
    return sent


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    load_dotenv()
    count = sweep()
    logger.info("Sweep complete. %d reminder(s) sent.", count)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_cron.py -v
```

Expected: all 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add cron/ tests/test_cron.py
git commit -m "feat: rule-based cron sweep with escalating reminder schedule"
```

---

## Task 12: Telegram bot listener

**Files:** Create `bot/telegram_bot.py`

- [ ] **Step 1: Create `bot/telegram_bot.py`**

```python
import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from ai.graph import run_graph
from bot.message import Message

logger = logging.getLogger(__name__)


async def _handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    user    = update.effective_user
    user_id = f"telegram:{user.id}"
    chat_id = str(update.effective_chat.id)
    logger.info("Telegram [%s]: %s", user_id, update.message.text[:80])

    msg = Message(platform="telegram", user_id=user_id, chat_id=chat_id, text=update.message.text)
    try:
        await update.message.chat.send_action("typing")
        reply = await asyncio.to_thread(run_graph, msg)
    except Exception as exc:
        logger.error("Telegram handler error: %s", exc, exc_info=True)
        reply = f"⚠️ Error: {type(exc).__name__}: {exc}"

    await update.message.reply_text(reply[:4096], parse_mode="HTML")


def run_telegram() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_message))
    logger.info("Telegram bot starting...")
    app.run_polling(drop_pending_updates=True)
```

- [ ] **Step 2: Smoke test**

```bash
python -c "from bot.telegram_bot import run_telegram; print('Telegram imports OK')"
```

Expected: `Telegram imports OK`

- [ ] **Step 3: Commit**

```bash
git add bot/telegram_bot.py
git commit -m "feat: Telegram bot listener"
```

---

## Task 13: Discord bot listener

**Files:** Create `bot/discord_bot.py`

- [ ] **Step 1: Create `bot/discord_bot.py`**

```python
import asyncio
import logging
import os

import discord

from ai.graph import run_graph
from bot.message import Message

logger = logging.getLogger(__name__)

_intents = discord.Intents.default()
_intents.message_content = True
_bot = discord.Client(intents=_intents)


@_bot.event
async def on_ready() -> None:
    logger.info("Discord bot ready as %s", _bot.user)


@_bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return  # DM-only

    user_id = f"discord:{message.author.id}"
    chat_id = str(message.channel.id)
    logger.info("Discord DM [%s]: %s", user_id, message.content[:80])

    msg = Message(platform="discord", user_id=user_id, chat_id=chat_id, text=message.content)
    try:
        async with message.channel.typing():
            reply = await asyncio.to_thread(run_graph, msg)
    except Exception as exc:
        logger.error("Discord handler error: %s", exc, exc_info=True)
        reply = f"⚠️ Error: {type(exc).__name__}: {exc}"

    await message.channel.send(reply[:2000])


def run_discord() -> None:
    token = os.environ["DISCORD_BOT_TOKEN"]
    logger.info("Discord bot starting...")
    _bot.run(token, log_handler=None)
```

- [ ] **Step 2: Smoke test**

```bash
python -c "from bot.discord_bot import run_discord; print('Discord imports OK')"
```

Expected: `Discord imports OK`

- [ ] **Step 3: Commit**

```bash
git add bot/discord_bot.py
git commit -m "feat: Discord DM bot listener"
```

---

## Task 14: Main entrypoint + Dockerfile

**Files:** Rewrite `main.py`, create `Dockerfile`

- [ ] **Step 1: Rewrite `main.py`**

```python
import logging
import os
import threading

from dotenv import load_dotenv


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    _configure_logging()
    load_dotenv()

    if os.environ.get("DISCORD_BOT_TOKEN"):
        from bot.discord_bot import run_discord
        threading.Thread(target=run_discord, name="discord-bot", daemon=True).start()

    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        from bot.telegram_bot import run_telegram
        run_telegram()
    else:
        raise EnvironmentError(
            "TELEGRAM_BOT_TOKEN is not set. Add it to .env."
        )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
```

- [ ] **Step 3: Run full unit test suite**

```bash
pytest tests/ -v --ignore=tests/test_db.py
```

Expected: all unit tests PASSED.

- [ ] **Step 4: Run integration tests**

```bash
pytest tests/test_db.py -m integration -v
```

Expected: all integration tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add main.py Dockerfile
git commit -m "feat: main entrypoint and Dockerfile"
```

---

## Task 15: Cron setup + push

- [ ] **Step 1: Add cron job**

```bash
crontab -e
```

Add (runs 8 AM daily):

```cron
0 8 * * * cd /home/thomas/repos/Smart_Reminder_System && /usr/bin/python3 -m cron.reminder_sweep >> /var/log/vehicle-reminders.log 2>&1
```

- [ ] **Step 2: Manual dry-run**

```bash
cd /home/thomas/repos/Smart_Reminder_System
python -m cron.reminder_sweep
```

Expected: log output showing sent count (0 is fine if no triggers fall today).

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 4: Verify CI**

Check `https://github.com/thomasjv799/Smart_Reminder_System/actions` — Lint workflow should pass.

---

## Self-review

- [x] Platform-agnostic `Message` dataclass → Task 2
- [x] `reminder_log` + `chat_messages` + `chat_summary` migrations → Task 3
- [x] Vehicle queries: all, expiring_soon, expired, by_owner, by_registration, by_nickname → Task 4
- [x] Field update whitelist (prevents injecting arbitrary column names) → Task 4
- [x] Reminder log deduplication → Task 5
- [x] Chat memory with 20-message summarisation threshold → Task 6
- [x] Notify util: Telegram + Discord, `notify()` dispatcher → Task 7
- [x] Groq provider with tool-call JSON parsing → Task 8
- [x] TOOLS list with confirmation rule baked into description → Task 9
- [x] LangGraph: load_memory → agent → execute_tools → save_memory loop → Task 10
- [x] Cron schedule: -30/-14/-7/-3/-1/0 before, +1/+3/+7/+15/+30 after → Task 11
- [x] 2-day catch-up window → Task 11
- [x] Telegram listener → Task 12
- [x] Discord DM listener → Task 13
- [x] main.py: Discord daemon thread + Telegram main thread → Task 14
- [x] Dockerfile → Task 14
- [x] Cron setup → Task 15
