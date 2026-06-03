import pytest
from datetime import date, timedelta
from unittest.mock import patch


def test_message_dataclass():
    from bot.message import Message
    msg = Message(platform="telegram", user_id="telegram:123", chat_id="456", text="hello")
    assert msg.platform == "telegram"
    assert msg.user_id == "telegram:123"
    assert msg.chat_id == "456"
    assert msg.text == "hello"


def test_format_vehicles_empty():
    from bot.functions import format_vehicles
    assert format_vehicles([]) == "No vehicles found."


def test_format_vehicles_countdown():
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
    requests_mock.post("https://api.telegram.org/bottok/sendMessage", json={"ok": True})
    notify("test message")
    assert requests_mock.called


def test_notify_unknown_platform():
    from utils.notify import notify
    with pytest.raises(ValueError, match="Unknown platform"):
        notify("msg", platform="carrier_pigeon")
