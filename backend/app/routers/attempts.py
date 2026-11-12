from fastapi import APIRouter

from app.db import connect
from app.repositories import orchestrations as orch_repo

router = APIRouter(tags=["attempts"])


@router.get("/attempts")
def list_attempts(orchestration_id: int | None = None):
    conn = connect()
    try:
        return orch_repo.list_attempts(conn, orchestration_id)
    finally:
        conn.close()
