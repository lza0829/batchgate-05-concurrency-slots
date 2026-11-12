from __future__ import annotations

import sqlite3

from app.engines.slots import (
    DEFAULT_CONCURRENCY,
    DEFAULT_SLOT_POLICY,
    normalize_limit,
    normalize_policy,
)

KEY_CONCURRENCY_LIMIT = "concurrency_limit"
KEY_SLOT_POLICY = "slot_overflow_policy"

DEFAULT_SETTINGS = {
    KEY_CONCURRENCY_LIMIT: str(DEFAULT_CONCURRENCY),
    KEY_SLOT_POLICY: DEFAULT_SLOT_POLICY,
}


def get_value(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if not row or row["value"] is None:
        return default
    return str(row["value"])


def set_value(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


def get_concurrency_limit(conn: sqlite3.Connection) -> int:
    raw = get_value(conn, KEY_CONCURRENCY_LIMIT, str(DEFAULT_CONCURRENCY))
    try:
        return normalize_limit(raw)
    except ValueError:
        return DEFAULT_CONCURRENCY


def get_slot_policy(conn: sqlite3.Connection) -> str:
    raw = get_value(conn, KEY_SLOT_POLICY, DEFAULT_SLOT_POLICY)
    try:
        return normalize_policy(raw)
    except ValueError:
        return DEFAULT_SLOT_POLICY
