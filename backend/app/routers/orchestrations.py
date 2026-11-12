from fastapi import APIRouter, HTTPException

from app.db import connect
from app.repositories import orchestrations as orch_repo
from app.schemas.entities import OrchestrationRunBody
from app.services.orchestrate_service import run_orchestration

router = APIRouter(tags=["orchestrations"])


@router.get("/orchestrations")
def list_orchestrations():
    conn = connect()
    try:
        return orch_repo.list_orchestrations(conn)
    finally:
        conn.close()


@router.get("/orchestrations/{orch_id}")
def get_orchestration(orch_id: int):
    conn = connect()
    try:
        row = orch_repo.get_orchestration(conn, orch_id)
        if not row:
            raise HTTPException(404, "not found")
        return row
    finally:
        conn.close()


@router.post("/orchestrations")
def create_orchestration(body: OrchestrationRunBody | None = None):
    try:
        return run_orchestration(
            concurrency_limit=body.concurrency_limit if body else None,
            slot_policy=body.slot_policy if body else None,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
