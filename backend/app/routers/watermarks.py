from fastapi import APIRouter

from app.db import connect
from app.repositories import watermarks as wm_repo

router = APIRouter(tags=["watermarks"])


@router.get("/watermarks")
def list_watermarks():
    conn = connect()
    try:
        return wm_repo.list_watermarks(conn)
    finally:
        conn.close()
