from __future__ import annotations

import json
from typing import Any

import sqlite3


def _row(r: sqlite3.Row | None) -> dict[str, Any] | None:
    if r is None:
        return None
    d = dict(r)
    d["depends_on"] = json.loads(d.pop("depends_on_json"))
    d["enabled"] = bool(d["enabled"])
    return d


def list_jobs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, fixture_path, depends_on_json, max_attempts, enabled, note FROM jobs ORDER BY id"
    ).fetchall()
    return [_row(r) for r in rows]  # type: ignore[misc]


def get_job(conn: sqlite3.Connection, job_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT id, name, fixture_path, depends_on_json, max_attempts, enabled, note FROM jobs WHERE id=?",
        (job_id,),
    ).fetchone()
    return _row(r)


def get_job_by_name(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT id, name, fixture_path, depends_on_json, max_attempts, enabled, note FROM jobs WHERE name=?",
        (name,),
    ).fetchone()
    return _row(r)


def update_max_attempts(conn: sqlite3.Connection, job_id: int, max_attempts: int) -> None:
    conn.execute("UPDATE jobs SET max_attempts=? WHERE id=?", (max_attempts, job_id))
