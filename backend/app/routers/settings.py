from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import connect
from app.engines.slots import (
    DEFAULT_CONCURRENCY,
    DEFAULT_SLOT_POLICY,
    MAX_CONCURRENCY,
    MIN_CONCURRENCY,
    SLOT_POLICIES,
    normalize_limit,
    normalize_policy,
)
from app.repositories import settings as settings_repo

router = APIRouter(tags=["settings"])


class SettingBody(BaseModel):
    value: str


class SlotSettingsBody(BaseModel):
    concurrency_limit: int = Field(ge=MIN_CONCURRENCY, le=MAX_CONCURRENCY)
    slot_policy: str = Field(pattern="^(wait|skip)$")


def _slot_payload(conn) -> dict:
    return {
        "concurrency_limit": settings_repo.get_concurrency_limit(conn),
        "slot_policy": settings_repo.get_slot_policy(conn),
        "default_concurrency_limit": DEFAULT_CONCURRENCY,
        "default_slot_policy": DEFAULT_SLOT_POLICY,
        "min_concurrency_limit": MIN_CONCURRENCY,
        "max_concurrency_limit": MAX_CONCURRENCY,
        "slot_policies": list(SLOT_POLICIES),
    }


@router.get("/settings")
def list_settings():
    conn = connect()
    try:
        rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/settings/slots")
def get_slot_settings():
    conn = connect()
    try:
        return _slot_payload(conn)
    finally:
        conn.close()


@router.put("/settings/slots")
def put_slot_settings(body: SlotSettingsBody):
    conn = connect()
    try:
        settings_repo.set_value(
            conn, settings_repo.KEY_CONCURRENCY_LIMIT, str(body.concurrency_limit)
        )
        settings_repo.set_value(
            conn, settings_repo.KEY_SLOT_POLICY, body.slot_policy
        )
        conn.commit()
        return _slot_payload(conn)
    finally:
        conn.close()


@router.put("/settings/{key}")
def put_setting(key: str, body: SettingBody):
    conn = connect()
    try:
        stored = body.value.strip()
        if key == settings_repo.KEY_CONCURRENCY_LIMIT:
            try:
                stored = str(normalize_limit(stored))
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        elif key == settings_repo.KEY_SLOT_POLICY:
            try:
                stored = normalize_policy(stored)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
        settings_repo.set_value(conn, key, stored)
        conn.commit()
        row = conn.execute("SELECT key, value FROM settings WHERE key=?", (key,)).fetchone()
        if not row:
            raise HTTPException(404, "not found")
        return dict(row)
    finally:
        conn.close()
