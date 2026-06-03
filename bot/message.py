from dataclasses import dataclass


@dataclass
class Message:
    platform: str   # "telegram" | "discord"
    user_id: str    # "{platform}:{id}", e.g. "telegram:123456"
    chat_id: str    # platform channel/chat ID used to send replies
    text: str
