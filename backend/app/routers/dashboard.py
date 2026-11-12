from fastapi import APIRouter

from app.services.orchestrate_service import dashboard_stats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard():
    return dashboard_stats()


@router.get("/health")
def health():
    return {"ok": True, "project": "batchgate"}
