"""In-process timing metrics.

Records how long things take and keeps the numbers in memory so `/metrics` can
render them. Three groups are tracked:

  request   whole HTTP requests, e.g. "POST /login"
  function  ``data.py`` calls, e.g. "find_user"
  query     SQL statements, e.g. "SELECT users"

plus two things specific to this app's design: how long opening the SQLite
connection takes, and how long threads spend **waiting** for ``db._lock``
before their statement can run. That wait is the contention number — with one
serialized connection it is what grows under concurrent load, not the SQL
itself.

Everything is bounded: at most ``_MAX_SAMPLES`` recent durations are kept per
name, which is enough for percentiles without growing without limit.
"""

from __future__ import annotations

import functools
import threading
import time
from collections import deque

_MAX_SAMPLES = 2000

GROUPS = ("request", "function", "query")

_lock = threading.Lock()
_started = time.time()

# group -> name -> {"count", "total", "min", "max", "samples"}
_series: dict = {group: {} for group in GROUPS}

# Opening the sqlite3 connection.
_connection = {"count": 0, "total": 0.0, "last": 0.0}

# db._lock contention.
_waiting = 0
_peak_waiting = 0


def _blank() -> dict:
    return {
        "count": 0,
        "total": 0.0,
        "min": float("inf"),
        "max": 0.0,
        "samples": deque(maxlen=_MAX_SAMPLES),
    }


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------
def record(group: str, name: str, seconds: float) -> None:
    """Add one timing sample."""
    with _lock:
        bucket = _series[group]
        entry = bucket.get(name)
        if entry is None:
            entry = bucket[name] = _blank()
        entry["count"] += 1
        entry["total"] += seconds
        entry["min"] = min(entry["min"], seconds)
        entry["max"] = max(entry["max"], seconds)
        entry["samples"].append(seconds)


def timed(group: str, name: str | None = None):
    """Decorator recording how long the wrapped function takes."""
    def decorate(func):
        label = name or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                record(group, label, time.perf_counter() - start)

        return wrapper

    return decorate


def record_connection(seconds: float) -> None:
    """Time taken by one ``sqlite3.connect`` call."""
    with _lock:
        _connection["count"] += 1
        _connection["total"] += seconds
        _connection["last"] = seconds


def wait_start() -> float:
    """Call immediately before acquiring the database lock."""
    global _waiting, _peak_waiting
    with _lock:
        _waiting += 1
        _peak_waiting = max(_peak_waiting, _waiting)
    return time.perf_counter()


def wait_end(start: float) -> None:
    """Call immediately after acquiring the database lock."""
    global _waiting
    waited = time.perf_counter() - start
    with _lock:
        _waiting -= 1
    record("query", "_lock wait", waited)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _percentile(ordered: list, fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted list."""
    if not ordered:
        return 0.0
    index = int(round(fraction * (len(ordered) - 1)))
    return ordered[index]


def _summarize(name: str, entry: dict) -> dict:
    ordered = sorted(entry["samples"])
    count = entry["count"]
    return {
        "name": name,
        "count": count,
        "total_ms": entry["total"] * 1000,
        "mean_ms": (entry["total"] / count) * 1000 if count else 0.0,
        "min_ms": (entry["min"] if count else 0.0) * 1000,
        "p50_ms": _percentile(ordered, 0.50) * 1000,
        "p95_ms": _percentile(ordered, 0.95) * 1000,
        "p99_ms": _percentile(ordered, 0.99) * 1000,
        "max_ms": entry["max"] * 1000,
        "sampled": len(ordered),
    }


def snapshot() -> dict:
    """A consistent copy of every metric, with durations in milliseconds."""
    with _lock:
        groups = {
            group: [(name, dict(entry, samples=list(entry["samples"])))
                    for name, entry in bucket.items()]
            for group, bucket in _series.items()
        }
        connection = dict(_connection)
        peak_waiting = _peak_waiting
        waiting = _waiting
        uptime = time.time() - _started

    return {
        "uptime_seconds": uptime,
        "connection": {
            "count": connection["count"],
            "total_ms": connection["total"] * 1000,
            "last_ms": connection["last"] * 1000,
            "mean_ms": (connection["total"] / connection["count"] * 1000)
                       if connection["count"] else 0.0,
        },
        "lock": {"waiting_now": waiting, "peak_waiting": peak_waiting},
        "groups": {
            group: sorted(
                (_summarize(name, entry) for name, entry in rows),
                key=lambda row: row["total_ms"],
                reverse=True,
            )
            for group, rows in groups.items()
        },
    }


def reset() -> None:
    """Drop every recorded sample and restart the clock."""
    global _series, _peak_waiting, _started
    with _lock:
        _series = {group: {} for group in GROUPS}
        _connection.update({"count": 0, "total": 0.0, "last": 0.0})
        _peak_waiting = 0
        _started = time.time()
