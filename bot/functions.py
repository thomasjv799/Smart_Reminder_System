from datetime import date, timedelta
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
            "name": "snooze_reminder",
            "description": (
                "Snooze or permanently ignore cron reminders for a specific vehicle document. "
                "Use when the user says they don't want reminders, plan to ignore renewal, "
                "or want to pause alerts for a period. "
                "To clear a snooze, call with mode='unsnooze'."
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
                        "description": "Which document to snooze",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["ignore", "snooze_days", "unsnooze"],
                        "description": (
                            "ignore=permanent, snooze_days=snooze for N days, unsnooze=clear"
                        ),
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to snooze (only for mode=snooze_days)",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional reason (e.g. 'vehicle sold', 'not renewing')",
                    },
                },
                "required": ["registration_number", "field", "mode"],
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
    if name == "snooze_reminder":
        return _snooze_reminder(arguments, user_id)
    return f"Unknown tool: {name}"


def _snooze_reminder(args: dict, user_id: str) -> str:
    reg   = args["registration_number"]
    field = args["field"]
    mode  = args["mode"]
    label = _FIELD_LABELS.get(field, field)

    vehicles = db.get_vehicles_filtered("by_registration", value=reg)
    if not vehicles:
        return f"Vehicle {reg} not found."
    vid = vehicles[0]["id"]

    if mode == "unsnooze":
        removed = db.unsnooze_reminder(vid, field)
        return f"Snooze cleared for {label} on {reg}." if removed else f"No active snooze for {label} on {reg}."

    until = None
    if mode == "snooze_days":
        days = args.get("days", 30)
        until = date.today() + timedelta(days=days)

    db.snooze_reminder(vid, field, until, args.get("reason", ""), user_id)
    if until:
        return f"Reminders for {label} on {reg} snoozed until {until}."
    return f"Reminders for {label} on {reg} permanently ignored."


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
        return f"Updated {label} for {args['registration_number']} to {args['new_date']}."
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
