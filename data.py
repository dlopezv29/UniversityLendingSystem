"""In-memory data store, accounts, and helpers.

Everything here is hardcoded and resets when the server restarts — no
database, no persistence. This module owns all mutable application state.
"""

from __future__ import annotations

import re
import secrets
from datetime import date

# ---------------------------------------------------------------------------
# Accounts & sessions (in-memory, reset on restart)
# ---------------------------------------------------------------------------
USERS: dict[str, dict] = {
    "admin": {"password": "password", "role": "admin"},
    "DGarcia": {"password": "password", "role": "professor", "professor": "Prof. García"},
}
SESSIONS: dict[str, str] = {}  # token -> username


def new_token() -> str:
    return secrets.token_hex(16)


# Words used to build human-readable return codes (e.g. "BRAVO-TANGO-4821").
_CODE_WORDS = [
    "BRAVO", "TANGO", "DELTA", "ZULU", "ECHO", "OMEGA",
    "SIERRA", "KILO", "LIMA", "NOVA", "ORION", "VEGA",
]


def generate_return_code() -> str:
    """A fresh random return code: two words plus a 4-digit number."""
    w1 = secrets.choice(_CODE_WORDS)
    w2 = secrets.choice(_CODE_WORDS)
    n = secrets.randbelow(10000)
    return f"{w1}-{w2}-{n:04d}"


# ---------------------------------------------------------------------------
# In-memory data store (resets on restart)
# ---------------------------------------------------------------------------
CATEGORIES = ["Monitors", "Peripherals", "Keys", "Controls"]

ITEMS: list[dict] = [
    {
        "id": "1",
        "name": "Dell Latitude Laptop",
        "category": "Peripherals",
        "description": "14-inch, Windows 11, charger included",
        "status": "available",
        "assigned_to": "",
        "assigned_on": "",
        "due_date": "",
    },
    {
        "id": "2",
        "name": "Epson Projector",
        "category": "Monitors",
        "description": "Full HD, HDMI + VGA",
        "status": "assigned",
        "assigned_to": "Prof. García",
        "assigned_on": "2026-06-20",
        "due_date": "2026-07-01",
    },
    {
        "id": "3",
        "name": "Logitech Webcam C920",
        "category": "Peripherals",
        "description": "1080p USB webcam",
        "status": "available",
        "assigned_to": "",
        "assigned_on": "",
        "due_date": "",
    },
]

PROFESSORS: list[dict] = [
    {"id": 1, "id_card": "PROF-001", "name": "Prof. García", "department": "Engineering"},
    {"id": 2, "id_card": "PROF-002", "name": "Prof. Rodríguez", "department": "Business"},
    {"id": 3, "id_card": "PROF-003", "name": "Prof. Jiménez", "department": "Arts & Sciences"},
]
NEXT_PROF_ID = 4


def find_item(item_id: str):
    """Return the item dict with the given id, or None."""
    for item in ITEMS:
        if item["id"] == item_id:
            return item
    return None


def valid_item_id(item_id: str) -> bool:
    """True if item_id is a well-formed free-text code (letters, numbers,
    dashes, underscores; non-empty)."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", item_id))


def find_professor(prof_id: int):
    """Return the professor dict with the given id, or None."""
    for prof in PROFESSORS:
        if prof["id"] == prof_id:
            return prof
    return None


def find_professor_by_id_card(id_card: str):
    """Return the professor dict with the given ID Card, or None."""
    for prof in PROFESSORS:
        if prof["id_card"] == id_card:
            return prof
    return None


def valid_id_card(id_card: str) -> bool:
    """Same rule as item IDs: letters, numbers, dashes, underscores; non-empty."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", id_card))


def is_overdue(item: dict) -> bool:
    return bool(
        item["status"] == "assigned"
        and item["due_date"]
        and item["due_date"] < date.today().isoformat()
    )


def add_item(item_id: str, name: str, category: str, description: str) -> dict:
    """Append a new available item with the caller-supplied id."""
    item = {
        "id": item_id,
        "name": name,
        "category": category,
        "description": description,
        "status": "available",
        "assigned_to": "",
        "assigned_on": "",
        "due_date": "",
    }
    ITEMS.append(item)
    return item


def add_professor(name: str, department: str, id_card: str) -> dict:
    """Append a new professor, owning the auto-increment id counter."""
    global NEXT_PROF_ID
    prof = {"id": NEXT_PROF_ID, "id_card": id_card, "name": name, "department": department}
    PROFESSORS.append(prof)
    NEXT_PROF_ID += 1
    return prof
