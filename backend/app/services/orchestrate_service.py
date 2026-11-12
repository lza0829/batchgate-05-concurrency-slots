from __future__ import annotations

from typing import Any

from app.config import FIXTURES_DIR
from app.db import connect
from app.engines.dependency import ready_by_upstream_success, topological_layers
from app.engines.job_runner import run_fixture_job
from app.engines.slots import (
    DISPOSITION_ACQUIRED,
    DISPOSITION_SKIPPED_SLOT,
    DISPOSITION_WAITED,
    LayerOutcome,
    SlotPool,
    normalize_limit,
    normalize_policy,
    run_layer,
)
from app.repositories import jobs as jobs_repo
from app.repositories import orchestrations as orch_repo
from app.repositories import settings as settings_repo
from app.repositories import watermarks as wm_repo

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"
STATUS_SKIPPED_DEP = "skipped_dep"
STATUS_SKIPPED_SLOT = "skipped_slot"


def _run_job_fixture(job: dict[str, Any]) -> dict[str, Any]:
    return run_fixture_job(FIXTURES_DIR / job["fixture_path"])


def dashboard_stats() -> dict[str, Any]:
    conn = connect()
    try:
        return {
            "job_count": conn.execute("SELECT COUNT(*) c FROM jobs").fetchone()["c"],
            "enabled_jobs": conn.execute(
                "SELECT COUNT(*) c FROM jobs WHERE enabled=1"
            ).fetchone()["c"],
            "orchestration_count": conn.execute(
                "SELECT COUNT(*) c FROM orchestrations"
            ).fetchone()["c"],
            "attempt_count": conn.execute(
                "SELECT COUNT(*) c FROM job_attempts"
            ).fetchone()["c"],
            "watermarked_jobs": conn.execute(
                "SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL"
            ).fetchone()["c"],
        }
    finally:
        conn.close()


def _attempt_summary(attempts: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "succeeded": 0,
        "failed": 0,
        "skipped_dep": 0,
        "skipped_slot": 0,
        "waited_then_acquired": 0,
    }
    for attempt in attempts:
        status = attempt["status"]
        detail = attempt.get("detail") or {}
        if status == STATUS_SUCCESS:
            counts["succeeded"] += 1
            if detail.get("disposition") == DISPOSITION_WAITED:
                counts["waited_then_acquired"] += 1
        elif status == STATUS_FAILED:
            counts["failed"] += 1
        elif status == STATUS_SKIPPED_DEP:
            counts["skipped_dep"] += 1
        elif status == STATUS_SKIPPED_SLOT:
            counts["skipped_slot"] += 1
    return counts


def run_orchestration(
    *,
    concurrency_limit: int | None = None,
    slot_policy: str | None = None,
) -> dict[str, Any]:
    """Run one orchestration.

    ``concurrency_limit`` / ``slot_policy`` override the saved settings for this
    run only; persisted settings are never mutated by a run.
    """
    conn = connect()
    try:
        jobs = [j for j in jobs_repo.list_jobs(conn) if j["enabled"]]
        limit = (
            normalize_limit(concurrency_limit)
            if concurrency_limit is not None
            else settings_repo.get_concurrency_limit(conn)
        )
        policy = (
            normalize_policy(slot_policy)
            if slot_policy is not None
            else settings_repo.get_slot_policy(conn)
        )
        orch_id = orch_repo.create_orchestration(conn)
        success_names: set[str] = set()
        layers = topological_layers(jobs)
        layer_reports: list[dict[str, Any]] = []

        for layer_index, layer in enumerate(layers):
            ready_jobs: list[dict[str, Any]] = []
            dep_skips: list[tuple[dict[str, Any], str]] = []
            for job in layer:
                ready, reason = ready_by_upstream_success(
                    job["depends_on"], success_names
                )
                if ready:
                    ready_jobs.append(job)
                else:
                    dep_skips.append((job, reason))

            # Only dependency-ready jobs compete for slots.
            pool = SlotPool(limit)
            outcomes: list[LayerOutcome | None] = [None] * len(ready_jobs)
            if ready_jobs:
                outcomes = run_layer(  # type: ignore[assignment]
                    ready_jobs,
                    limit=limit,
                    policy=policy,
                    run_job=_run_job_fixture,
                    pool=pool,
                )
            layer_peak = pool.peak_active

            by_job_id = {o.job["id"]: o for o in outcomes if o is not None}
            layer_dispositions = {
                DISPOSITION_ACQUIRED: 0,
                DISPOSITION_WAITED: 0,
                DISPOSITION_SKIPPED_SLOT: 0,
            }
            admitted_total = 0

            # Insert attempts in the layer's declared order so the audit trail is
            # stable and every job in the layer is accounted for exactly once.
            for job in layer:
                outcome = by_job_id.get(job["id"])
                if outcome is None:
                    reason = next(
                        reason for skipped_job, reason in dep_skips
                        if skipped_job["id"] == job["id"]
                    )
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=1,
                        status=STATUS_SKIPPED_DEP,
                        detail={"reason": reason},
                    )
                    continue

                decision = outcome.decision
                layer_dispositions[decision.disposition] += 1
                if decision.admitted:
                    admitted_total += 1

                if not decision.admitted:
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=1,
                        status=STATUS_SKIPPED_SLOT,
                        detail={
                            "reason": (
                                f"layer {layer_index} concurrency limit {limit} reached; "
                                f"policy=skip, queue_position={decision.queue_position}"
                            ),
                            **outcome.as_detail(),
                            "slot_state": "not_acquired",
                        },
                    )
                    continue

                if outcome.error is not None:
                    orch_repo.insert_attempt(
                        conn,
                        orchestration_id=orch_id,
                        job_id=job["id"],
                        attempt_no=1,
                        status=STATUS_FAILED,
                        detail={
                            "error": outcome.error,
                            **outcome.as_detail(),
                            "slot_state": "released_after_failure",
                        },
                    )
                    continue

                result = outcome.result or {}
                orch_repo.insert_attempt(
                    conn,
                    orchestration_id=orch_id,
                    job_id=job["id"],
                    attempt_no=1,
                    status=STATUS_SUCCESS,
                    detail={
                        **result,
                        **outcome.as_detail(),
                        "slot_state": "released",
                    },
                )
                wm_repo.set_watermark(
                    conn, job["id"], result["watermark_ts"], result["artifact_rows"]
                )
                success_names.add(job["name"])

            layer_reports.append(
                {
                    "layer": layer_index,
                    "job_total": len(layer),
                    "slot_limit": limit,
                    "slot_policy": policy,
                    "dispositions": layer_dispositions,
                    "skipped_dep": len(dep_skips),
                    "waves": -(-admitted_total // limit) if admitted_total else 0,
                    "peak_concurrency": layer_peak,
                }
            )

        # Derive every report count from the persisted attempt rows so the report
        # can never drift from the attempt list.
        attempts = orch_repo.list_attempts(conn, orch_id)
        counts = _attempt_summary(attempts)
        skipped_total = counts["skipped_dep"] + counts["skipped_slot"]
        report = {
            "orchestration_id": orch_id,
            "job_total": len(jobs),
            "succeeded": counts["succeeded"],
            "failed": counts["failed"],
            "skipped": skipped_total,
            "skipped_dep": counts["skipped_dep"],
            "skipped_slot": counts["skipped_slot"],
            "waited_then_acquired": counts["waited_then_acquired"],
            "attempt_count": len(attempts),
            "concurrency_limit": limit,
            "slot_policy": policy,
            "watermarked_jobs": conn.execute(
                "SELECT COUNT(*) c FROM watermarks WHERE watermark_ts IS NOT NULL"
            ).fetchone()["c"],
            "layer_count": len(layers),
            "layers": layer_reports,
        }
        status = (
            "ok"
            if counts["failed"] == 0 and counts["skipped_slot"] == 0
            else "partial"
        )
        orch_repo.finish_orchestration(conn, orch_id, status, report)
        conn.commit()
        return orch_repo.get_orchestration(conn, orch_id) or report
    finally:
        conn.close()
