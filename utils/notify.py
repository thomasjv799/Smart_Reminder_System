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
