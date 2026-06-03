from utils.telegram_ import send_telegram

_CHANNELS: dict = {
    "telegram": send_telegram,
}


def notify(message: str, channels: list[str] | None = None) -> None:
    """Dispatch message to one or more named channels (default: telegram)."""
    for ch in channels or ["telegram"]:
        _CHANNELS[ch](message)
