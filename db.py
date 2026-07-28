"""SQLite connection, schema, and seed data.

This is the only module that imports ``sqlite3``. Everything above it talks to
``data.py``, which speaks in plain dicts.

The server is a ``ThreadingHTTPServer`` (one thread per request) and sqlite3
connections are not thread-safe, so we keep a single connection opened with
``check_same_thread=False`` and serialize every statement behind a lock. Traffic
here is a handful of requests per minute; a connection pool would be noise.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time

import metrics

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lending.db")

_conn: sqlite3.Connection | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS professors (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_card    TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS items (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    category       TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT 'available'
                   CHECK (status IN ('available', 'assigned', 'disabled')),
    assigned_to_id INTEGER REFERENCES professors(id) ON DELETE RESTRICT,
    assigned_on    TEXT NOT NULL DEFAULT '',
    due_date       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS users (
    username     TEXT PRIMARY KEY,
    password     TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('admin', 'professor')),
    professor_id INTEGER REFERENCES professors(id) ON DELETE SET NULL
);
"""


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def connect() -> sqlite3.Connection:
    """Return the shared connection, opening it on first use."""
    global _conn
    if _conn is None:
        start = time.perf_counter()
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # SQLite ignores foreign keys unless you ask for them, every connection.
        _conn.execute("PRAGMA foreign_keys = ON")
        metrics.record_connection(time.perf_counter() - start)
    return _conn


def close() -> None:
    """Close the shared connection (used by tests)."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


_label_cache: dict = {}


def _label(sql: str) -> str:
    """A short metric name for a statement, e.g. "SELECT users"."""
    cached = _label_cache.get(sql)
    if cached:
        return cached

    words = sql.replace("(", " ").replace(",", " ").split()
    verb = words[0].upper() if words else "SQL"
    table = ""
    upper = [w.upper() for w in words]
    if verb in ("SELECT", "DELETE") and "FROM" in upper:
        table = words[upper.index("FROM") + 1]
    elif verb == "INSERT" and "INTO" in upper:
        table = words[upper.index("INTO") + 1]
    elif verb == "UPDATE" and len(words) > 1:
        table = words[1]
    label = f"{verb} {table}".strip()
    _label_cache[sql] = label
    return label


def query(sql: str, params: tuple = ()) -> list:
    """Run a SELECT and return all rows."""
    waited = metrics.wait_start()
    with _lock:
        metrics.wait_end(waited)
        start = time.perf_counter()
        try:
            return connect().execute(sql, params).fetchall()
        finally:
            metrics.record("query", _label(sql), time.perf_counter() - start)


def query_one(sql: str, params: tuple = ()):
    """Run a SELECT and return the first row, or None."""
    waited = metrics.wait_start()
    with _lock:
        metrics.wait_end(waited)
        start = time.perf_counter()
        try:
            return connect().execute(sql, params).fetchone()
        finally:
            metrics.record("query", _label(sql), time.perf_counter() - start)


def execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    """Run an INSERT/UPDATE/DELETE and commit.

    Raises sqlite3.IntegrityError when a constraint rejects the write; callers
    in ``data.py`` translate that into a user-facing error.
    """
    waited = metrics.wait_start()
    with _lock:
        metrics.wait_end(waited)
        start = time.perf_counter()
        try:
            conn = connect()
            cursor = conn.execute(sql, params)
            conn.commit()
            return cursor
        finally:
            metrics.record("query", _label(sql), time.perf_counter() - start)


# ---------------------------------------------------------------------------
# Seed data — the values this app used to hardcode in data.py
# ---------------------------------------------------------------------------
_SEED_PROFESSORS = [
    ("PROF-001", "Prof. García", "Engineering"),
    ("PROF-002", "Prof. Rodríguez", "Business"),
    ("PROF-003", "Prof. Jiménez", "Arts & Sciences"),
]

_SEED_ITEMS = [
    ("1", "Dell Latitude Laptop", "Peripherals",
     "14-inch, Windows 11, charger included", "available", None, "", ""),
    ("2", "Epson Projector", "Monitors",
     "Full HD, HDMI + VGA", "assigned", "PROF-001", "2026-06-20", "2026-07-01"),
    ("3", "Logitech Webcam C920", "Peripherals",
     "1080p USB webcam", "available", None, "", ""),
]

# (username, password, role, professor id_card or None)
_SEED_USERS = [
    ("admin", "password", "admin", None),
    ("DGarcia", "password", "professor", "PROF-001"),
]


def _seed(conn: sqlite3.Connection) -> None:
    """Insert the demo rows. Only called on a database with no professors."""
    prof_ids = {}
    for id_card, name, department in _SEED_PROFESSORS:
        cursor = conn.execute(
            "INSERT INTO professors (id_card, name, department) VALUES (?, ?, ?)",
            (id_card, name, department),
        )
        prof_ids[id_card] = cursor.lastrowid

    for item_id, name, category, desc, status, card, on, due in _SEED_ITEMS:
        conn.execute(
            "INSERT INTO items (id, name, category, description, status,"
            " assigned_to_id, assigned_on, due_date)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, name, category, desc, status,
             prof_ids.get(card) if card else None, on, due),
        )

    for username, password, role, card in _SEED_USERS:
        conn.execute(
            "INSERT INTO users (username, password, role, professor_id)"
            " VALUES (?, ?, ?, ?)",
            (username, password, role, prof_ids.get(card) if card else None),
        )


def init() -> None:
    """Create the schema if missing, and seed a brand-new database."""
    with _lock:
        conn = connect()
        conn.executescript(SCHEMA)
        empty = conn.execute("SELECT COUNT(*) FROM professors").fetchone()[0] == 0
        if empty:
            _seed(conn)
        conn.commit()
