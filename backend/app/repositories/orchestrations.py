from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import sqlite3


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def create_orchestration(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO orchestrations(status, started_at, finished_at, report_json) VALUES (?,?,?,?)",
        ("running", _now(), None, "{}"),
    )
    return int(cur.lastrowid)


def finish_orchestration(
    conn: sqlite3.Connection,
    orch_id: int,
    status: str,
    report: dict[str, Any],
) -> None:
    conn.execute(
        "UPDATE orchestrations SET status=?, finished_at=?, report_json=? WHERE id=?",
        (status, _now(), json.dumps(report, ensure_ascii=False), orch_id),
    )


def get_orchestration(conn: sqlite3.Connection, orch_id: int) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT id, status, started_at, finished_at, report_json FROM orchestrations WHERE id=?",
        (orch_id,),
    ).fetchone()
    if not r:
        return None
    d = dict(r)
    d["report"] = json.loads(d.pop("report_json"))
    return d


def list_orchestrations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, status, started_at, finished_at, report_json FROM orchestrations ORDER BY id DESC"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["report"] = json.loads(d.pop("report_json"))
        out.append(d)
    return out


def insert_attempt(
    conn: sqlite3.Connection,
    *,
    orchestration_id: int,
    job_id: int,
    attempt_no: int,
    status: str,
    detail: dict[str, Any],
) -> int:
    cur = conn.execute(
        """
        INSERT INTO job_attempts(orchestration_id, job_id, attempt_no, status, detail, created_at)
        VALUES (?,?,?,?,?,?)
        """,
        (
            orchestration_id,
            job_id,
            attempt_no,
            status,
            json.dumps(detail, ensure_ascii=False),
            _now(),
        ),
    )
    return int(cur.lastrowid)


def list_attempts(
    conn: sqlite3.Connection, orchestration_id: int | None = None
) -> list[dict[str, Any]]:
    if orchestration_id is None:
        rows = conn.execute(
            """
            SELECT a.id, a.orchestration_id, a.job_id, j.name AS job_name,
                   a.attempt_no, a.status, a.detail, a.created_at
            FROM job_attempts a JOIN jobs j ON j.id=a.job_id
            ORDER BY a.id DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT a.id, a.orchestration_id, a.job_id, j.name AS job_name,
                   a.attempt_no, a.status, a.detail, a.created_at
            FROM job_attempts a JOIN jobs j ON j.id=a.job_id
            WHERE a.orchestration_id=?
            ORDER BY a.id
            """,
            (orchestration_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["detail"] = json.loads(d.pop("detail"))
        out.append(d)
    return out
