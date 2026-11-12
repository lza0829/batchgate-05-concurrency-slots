from fastapi import APIRouter, HTTPException

from app.db import connect
from app.repositories import jobs as jobs_repo
from app.schemas.entities import MaxAttemptsBody

router = APIRouter(tags=["jobs"])


@router.get("/jobs")
def list_jobs():
    conn = connect()
    try:
        return jobs_repo.list_jobs(conn)
    finally:
        conn.close()


@router.patch("/jobs/{job_id}/max-attempts")
def patch_max_attempts(job_id: int, body: MaxAttemptsBody):
    conn = connect()
    try:
        job = jobs_repo.get_job(conn, job_id)
        if not job:
            raise HTTPException(404, "job not found")
        jobs_repo.update_max_attempts(conn, job_id, body.max_attempts)
        conn.commit()
        return jobs_repo.get_job(conn, job_id)
    finally:
        conn.close()
