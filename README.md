# Smart Reminder System

A Python script that queries a self-hosted PostgreSQL database for upcoming vehicle
document expirations and sends reminders via Telegram.

## What it tracks

| Field | Reminder threshold |
|---|---|
| Insurance | configurable (default 30 days) |
| Pollution (PUCC) | same |
| Fitness / RC validity | same |
| MV Tax | same |
| Permit (commercial vehicles) | same |

It also catches items that expired within the last 7 days, in case the script missed a run.

## Architecture

```
Postgres (vehicles table)
        |
    main.py
        |
   utils/notify.py  ──▶  Telegram
                    ──▶  (other channels — extend notify.py)
```

Runs as a cron job on the same machine as the database — no Tailscale traversal needed.

## Prerequisites

- Python 3.11+
- A running PostgreSQL instance with the `vehicles` table (see [Master_DB_Postgres](https://github.com/thomasjv799/Master_DB_Postgres))
- A Telegram bot token (create one via [@BotFather](https://t.me/BotFather))
- Your Telegram chat ID (get it from [@userinfobot](https://t.me/userinfobot))

## Setup

```bash
git clone git@github.com:thomasjv799/Smart_Reminder_System.git
cd Smart_Reminder_System

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env with your DATABASE_URI, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

## Running

```bash
source .venv/bin/activate
python main.py
```

Or with a different lookahead window:

```bash
REMINDER_DAYS=14 python main.py
```

## Scheduling (cron)

Add to crontab (`crontab -e`) to run every morning at 8 AM:

```cron
0 8 * * * cd /path/to/Smart_Reminder_System && /path/to/.venv/bin/python main.py >> /var/log/vehicle-reminders.log 2>&1
```

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URI` | PostgreSQL connection string | required |
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather | required |
| `TELEGRAM_CHAT_ID` | Target chat/group ID | required |
| `REMINDER_DAYS` | Look-ahead window in days | `30` |

## Adding notification channels

`utils/notify.py` maps channel names to send functions. To add a new channel (e.g. WhatsApp):

1. Add a `utils/whatsapp_.py` with a `send_whatsapp(message: str) -> None` function.
2. Register it in `utils/notify.py`:
   ```python
   from utils.whatsapp_ import send_whatsapp
   _CHANNELS = {
       "telegram": send_telegram,
       "whatsapp": send_whatsapp,
   }
   ```
3. Call `notify(msg, channels=["telegram", "whatsapp"])` in `main.py`.

## License

MIT — see `LICENSE.txt`.
