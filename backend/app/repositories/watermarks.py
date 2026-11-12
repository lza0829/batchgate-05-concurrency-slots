from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import sqlite3


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_watermarks(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT w.job_id, j.name AS job_name, w.watermark_ts, w.artifact_rows, w.updated_at
        FROM watermarks w JOIN jobs j ON j.id=w.job_id
        ORDER BY w.job_id
        """
    ).fetchall()
    return [dict(r) for r in rows]


def set_watermark(
    conn: sqlite3.Connection, job_id: int, watermark_ts: str, artifact_rows: int
) -> None:
    conn.execute(
        """
        INSERT INTO watermarks(job_id, watermark_ts, artifact_rows, updated_at)
        VALUES (?,?,?,?)
        ON CONFLICT(job_id) DO UPDATE SET
          watermark_ts=excluded.watermark_ts,
          artifact_rows=excluded.artifact_rows,
          updated_at=excluded.updated_at
        """,
        (job_id, watermark_ts, artifact_rows, _now()),
    )
