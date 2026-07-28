"""Data access layer: items, professors, accounts, sessions, and helpers.

State lives in a local SQLite file (see ``db.py``) and survives restarts. This
module is the only thing the rest of the app talks to, and it speaks in plain
dicts — the same shapes ``views.py`` has always rendered.

One detail worth knowing: in the database an item points at a professor by id
(``items.assigned_to_id``), but every read here joins that back to the
professor's name and exposes it as ``item["assigned_to"]``. Callers keep working
with names; the database keeps referential integrity. A professor rename now
updates all of their loans for free.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import date

import db
import metrics

# ---------------------------------------------------------------------------
# Sessions (in-memory on purpose — tokens should not survive a restart)
# ---------------------------------------------------------------------------
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


# A fixed vocabulary the admin cannot edit, so it stays a constant rather than
# a table.
CATEGORIES = ["Monitors", "Peripherals", "Keys", "Controls"]


# ---------------------------------------------------------------------------
# Validation helpers (pure)
# ---------------------------------------------------------------------------
def valid_item_id(item_id: str) -> bool:
    """True if item_id is a well-formed free-text code (letters, numbers,
    dashes, underscores; non-empty)."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", item_id))


def valid_id_card(id_card: str) -> bool:
    """Same rule as item IDs: letters, numbers, dashes, underscores; non-empty."""
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", id_card))


def is_overdue(item: dict) -> bool:
    return bool(
        item["status"] == "assigned"
        and item["due_date"]
        and item["due_date"] < date.today().isoformat()
    )


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------
_ITEM_SELECT = """
    SELECT i.id, i.name, i.category, i.description, i.status,
           COALESCE(p.name, '') AS assigned_to,
           i.assigned_on, i.due_date
    FROM items i
    LEFT JOIN professors p ON p.id = i.assigned_to_id
"""


@metrics.timed("function")
def all_items() -> list:
    """Every item, oldest first, as dicts."""
    return [dict(row) for row in db.query(_ITEM_SELECT + " ORDER BY i.rowid")]


@metrics.timed("function")
def find_item(item_id: str):
    """Return the item dict with the given id, or None."""
    row = db.query_one(_ITEM_SELECT + " WHERE i.id = ?", (item_id,))
    return dict(row) if row else None


@metrics.timed("function")
def available_items() -> list:
    """Items that can currently be lent out."""
    return [
        dict(row)
        for row in db.query(
            _ITEM_SELECT + " WHERE i.status = 'available' ORDER BY i.rowid"
        )
    ]


@metrics.timed("function")
def find_available_item_by_name(name: str):
    """First available item with this exact name, or None."""
    row = db.query_one(
        _ITEM_SELECT + " WHERE i.name = ? AND i.status = 'available' ORDER BY i.rowid",
        (name,),
    )
    return dict(row) if row else None


@metrics.timed("function")
def add_item(item_id: str, name: str, category: str, description: str):
    """Insert a new available item with the caller-supplied id.

    Returns the new item dict, or None if the id is already taken — the
    database decides, so two concurrent requests cannot both win.
    """
    try:
        db.execute(
            "INSERT INTO items (id, name, category, description, status)"
            " VALUES (?, ?, ?, ?, 'available')",
            (item_id, name, category, description),
        )
    except sqlite3.IntegrityError:
        return None
    return find_item(item_id)


@metrics.timed("function")
def update_item(item_id: str, name: str, category: str, description: str) -> None:
    """Update an item's editable fields. Blank name or unknown category are
    left as they were, matching the old edit behavior."""
    item = find_item(item_id)
    if not item:
        return
    db.execute(
        "UPDATE items SET name = ?, category = ?, description = ? WHERE id = ?",
        (
            name or item["name"],
            category if category in CATEGORIES else item["category"],
            description,
            item_id,
        ),
    )


@metrics.timed("function")
def delete_item(item_id: str) -> None:
    db.execute("DELETE FROM items WHERE id = ?", (item_id,))


@metrics.timed("function")
def set_item_status(item_id: str, status: str) -> None:
    db.execute("UPDATE items SET status = ? WHERE id = ?", (status, item_id))


@metrics.timed("function")
def assign_item(item_id: str, professor_id: int, assigned_on: str, due_date: str) -> None:
    """Lend an item to a professor."""
    db.execute(
        "UPDATE items SET status = 'assigned', assigned_to_id = ?,"
        " assigned_on = ?, due_date = ? WHERE id = ?",
        (professor_id, assigned_on, due_date, item_id),
    )


@metrics.timed("function")
def return_item(item_id: str) -> None:
    """Take an item back: clear the assignee and both dates."""
    db.execute(
        "UPDATE items SET status = 'available', assigned_to_id = NULL,"
        " assigned_on = '', due_date = '' WHERE id = ?",
        (item_id,),
    )


# ---------------------------------------------------------------------------
# Professors
# ---------------------------------------------------------------------------
_PROF_SELECT = "SELECT id, id_card, name, department FROM professors"


@metrics.timed("function")
def all_professors() -> list:
    return [dict(row) for row in db.query(_PROF_SELECT + " ORDER BY id")]


@metrics.timed("function")
def find_professor(prof_id: int):
    """Return the professor dict with the given id, or None."""
    row = db.query_one(_PROF_SELECT + " WHERE id = ?", (prof_id,))
    return dict(row) if row else None


@metrics.timed("function")
def find_professor_by_id_card(id_card: str):
    """Return the professor dict with the given ID Card, or None."""
    row = db.query_one(_PROF_SELECT + " WHERE id_card = ?", (id_card,))
    return dict(row) if row else None


@metrics.timed("function")
def find_professor_by_name(name: str):
    """Return the first professor with this exact name, or None."""
    row = db.query_one(_PROF_SELECT + " WHERE name = ? ORDER BY id", (name,))
    return dict(row) if row else None


@metrics.timed("function")
def add_professor(name: str, department: str, id_card: str):
    """Insert a professor. Returns the new dict, or None if the ID Card is taken."""
    try:
        cursor = db.execute(
            "INSERT INTO professors (id_card, name, department) VALUES (?, ?, ?)",
            (id_card, name, department),
        )
    except sqlite3.IntegrityError:
        return None
    return find_professor(cursor.lastrowid)


@metrics.timed("function")
def update_professor(prof_id: int, id_card: str, name: str, department: str) -> bool:
    """Update a professor. Returns False if the ID Card belongs to someone else."""
    prof = find_professor(prof_id)
    if not prof:
        return True
    try:
        db.execute(
            "UPDATE professors SET id_card = ?, name = ?, department = ? WHERE id = ?",
            (id_card, name or prof["name"], department, prof_id),
        )
    except sqlite3.IntegrityError:
        return False
    return True


@metrics.timed("function")
def delete_professor(prof_id: int) -> bool:
    """Remove a professor. Returns False if the database refuses because they
    still hold items (ON DELETE RESTRICT)."""
    try:
        db.execute("DELETE FROM professors WHERE id = ?", (prof_id,))
    except sqlite3.IntegrityError:
        return False
    return True


@metrics.timed("function")
def items_assigned_to(professor_id: int) -> list:
    """The professor's currently assigned (not returned) items."""
    return [
        dict(row)
        for row in db.query(
            _ITEM_SELECT
            + " WHERE i.assigned_to_id = ? AND i.status = 'assigned' ORDER BY i.rowid",
            (professor_id,),
        )
    ]


@metrics.timed("function")
def professor_active_item_count(professor_id: int) -> int:
    return db.query_one(
        "SELECT COUNT(*) AS n FROM items"
        " WHERE assigned_to_id = ? AND status = 'assigned'",
        (professor_id,),
    )["n"]


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
@metrics.timed("function")
def find_user(username: str):
    """Return {'name', 'password', 'role', 'professor'} or None.

    ``professor`` is the linked professor's name (empty for admins), resolved
    through the foreign key.
    """
    row = db.query_one(
        "SELECT u.username, u.password, u.role, COALESCE(p.name, '') AS professor"
        " FROM users u LEFT JOIN professors p ON p.id = u.professor_id"
        " WHERE u.username = ?",
        (username,),
    )
    if not row:
        return None
    return {
        "name": row["username"],
        "password": row["password"],
        "role": row["role"],
        "professor": row["professor"],
    }
