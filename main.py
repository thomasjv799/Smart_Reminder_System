import os
import sys
from datetime import date

from utils.db import get_expiring_vehicles
from utils.notify import notify

REMINDER_DAYS = int(os.getenv("REMINDER_DAYS", "30"))

_EXPIRY_LABELS = {
    "insurance_valid_until": "Insurance",
    "pucc_valid_until":      "Pollution (PUCC)",
    "fitness_valid_until":   "Fitness / RC validity",
    "mv_tax_valid_until":    "MV Tax",
    "permit_valid_until":    "Permit",
}


def build_messages(vehicles: list[dict], days: int) -> list[str]:
    today = date.today()
    msgs = []
    for v in vehicles:
        label = v["nickname"] or v["registration_number"]
        for col, kind in _EXPIRY_LABELS.items():
            expiry = v[col]
            if expiry is None:
                continue
            remaining = (expiry - today).days
            if remaining > days:
                continue
            if remaining < 0:
                status = f"EXPIRED {-remaining}d ago"
            elif remaining == 0:
                status = "expires TODAY"
            else:
                status = f"in {remaining}d"
            msgs.append(
                f"<b>{kind}</b> — {label} ({v['registration_number']})\n"
                f"Owner: {v['owner_name'] or 'Unknown'}  |  {expiry}  ({status})"
            )
    return msgs


def main() -> None:
    vehicles = get_expiring_vehicles(REMINDER_DAYS)
    msgs = build_messages(vehicles, REMINDER_DAYS)

    if not msgs:
        print("No upcoming expirations.")
        return

    header = (
        f"<b>Vehicle Reminders</b> — {date.today()}\n"
        f"{len(msgs)} item(s) within {REMINDER_DAYS} days\n"
    )
    notify(header + "\n" + "\n\n".join(msgs))
    print(f"Sent {len(msgs)} reminder(s).")


if __name__ == "__main__":
    main()
