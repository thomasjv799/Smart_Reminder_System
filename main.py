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
        raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set. Add it to .env.")


if __name__ == "__main__":
    main()
