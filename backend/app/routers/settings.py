from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import connect

router = APIRouter(tags=["settings"])


class SettingBody(BaseModel):
    value: str


@router.get("/settings")
def list_settings():
    conn = connect()
    try:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingBody):
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, body.value),
        )
        conn.commit()
        row = conn.execute("SELECT key, value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        return dict(row)
    finally:
        conn.close()
