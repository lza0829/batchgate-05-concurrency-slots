from __future__ import annotations

import pytest

from app import db as db_module
from app.db import connect
from app.repositories import settings as settings_repo
from app.seed import init_db
from app.services.orchestrate_service import run_orchestration


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db_module, "DATA_DIR", tmp_path)
    init_db()
    yield
    db_module.DB_PATH.unlink(missing_ok=True)


def _attempts(orch_id: int) -> list[dict]:
    conn = connect()
    try:
        from app.repositories import orchestrations as orch_repo

        return orch_repo.list_attempts(conn, orch_id)
    finally:
        conn.close()


def _set_slots(limit: int, policy: str) -> None:
    conn = connect()
    try:
        settings_repo.set_value(conn, settings_repo.KEY_CONCURRENCY_LIMIT, str(limit))
        settings_repo.set_value(conn, settings_repo.KEY_SLOT_POLICY, policy)
        conn.commit()
    finally:
        conn.close()


def _assert_report_matches_attempts(run: dict) -> list[dict]:
    report = run["report"]
    attempts = _attempts(run["id"])
    assert report["attempt_count"] == len(attempts) == report["job_total"]
    assert len({a["job_id"] for a in attempts}) == len(attempts)
    statuses = [a["status"] for a in attempts]
    assert report["succeeded"] == statuses.count("success")
    assert report["failed"] == statuses.count("failed")
    assert report["skipped_dep"] == statuses.count("skipped_dep")
    assert report["skipped_slot"] == statuses.count("skipped_slot")
    assert report["skipped"] == statuses.count("skipped_dep") + statuses.count(
        "skipped_slot"
    )
    waited = [
        a for a in attempts
        if a["detail"].get("disposition") == "waited_then_acquired"
    ]
    assert report["waited_then_acquired"] == len(waited)
    return attempts


def test_slots_are_enough_to_finish(isolated_db):
    _set_slots(3, "wait")
    run = run_orchestration()
    attempts = _assert_report_matches_attempts(run)
    assert run["status"] == "ok"
    assert run["report"]["succeeded"] == 3
    assert run["report"]["skipped_slot"] == 0
    assert run["report"]["waited_then_acquired"] == 0
    assert all(a["status"] == "success" for a in attempts)
    assert all(a["detail"]["disposition"] == "acquired" for a in attempts)
    for a in attempts:
        detail = a["detail"]
        assert detail["slot_state"] == "released"
        assert detail["slot_index"] in (0, 1, 2)
        assert detail["released_at"] >= detail["acquired_at"]
        assert detail["planned_wave"] == 0
    # Layer 0 really ran both jobs at once because two slots were free.
    assert run["report"]["layers"][0]["peak_concurrency"] == 2
    assert run["report"]["layers"][0]["waves"] == 1
    assert all(l["dispositions"]["skipped_slot"] == 0 for l in run["report"]["layers"])


def test_wait_policy_records_wait_then_success(isolated_db):
    # Layer 0 has two ready jobs; limit 1 forces the second one to wait.
    _set_slots(1, "wait")
    run = run_orchestration()
    attempts = _assert_report_matches_attempts(run)
    assert run["status"] == "ok"
    assert run["report"]["succeeded"] == 3
    assert run["report"]["skipped_slot"] == 0
    assert run["report"]["waited_then_acquired"] == 1
    waited = [
        a for a in attempts
        if a["detail"].get("disposition") == "waited_then_acquired"
    ]
    assert len(waited) == 1
    assert waited[0]["status"] == "success"
    assert waited[0]["detail"]["queue_position"] == 1
    assert waited[0]["detail"]["planned_wave"] == 1
    # The waiting job took the only slot after the first wave released it.
    assert all(a["detail"]["slot_state"] == "released" for a in attempts)
    assert all(a["detail"]["slot_index"] == 0 for a in attempts)
    assert run["report"]["layers"][0]["peak_concurrency"] == 1
    assert run["report"]["layers"][0]["waves"] == 2


def test_skip_policy_records_skipped_slot(isolated_db):
    _set_slots(1, "skip")
    run = run_orchestration()
    attempts = _assert_report_matches_attempts(run)
    skipped = [a for a in attempts if a["status"] == "skipped_slot"]
    assert len(skipped) == 1
    assert skipped[0]["detail"]["policy"] == "skip"
    assert skipped[0]["detail"]["disposition"] == "skipped_slot"
    assert skipped[0]["detail"]["slot_state"] == "not_acquired"
    assert "slot_index" not in skipped[0]["detail"]
    assert "concurrency limit 1" in skipped[0]["detail"]["reason"]
    assert run["report"]["skipped_slot"] == 1
    assert run["status"] == "partial"
    # The skipped job's downstream cannot run and is recorded as a dependency skip.
    dep = [a for a in attempts if a["status"] == "skipped_dep"]
    assert len(dep) == 1


def test_per_run_override_does_not_change_saved_settings(isolated_db):
    _set_slots(3, "wait")
    run = run_orchestration(concurrency_limit=1, slot_policy="skip")
    _assert_report_matches_attempts(run)
    assert run["report"]["concurrency_limit"] == 1
    assert run["report"]["slot_policy"] == "skip"
    conn = connect()
    try:
        assert settings_repo.get_concurrency_limit(conn) == 3
        assert settings_repo.get_slot_policy(conn) == "wait"
    finally:
        conn.close()


def test_failure_releases_slot_and_report_stays_consistent(isolated_db, monkeypatch):
    import app.services.orchestrate_service as svc

    real = svc._run_job_fixture

    def flaky(job):
        if job["name"] == "ingest_orders":
            raise RuntimeError("fixture exploded")
        return real(job)

    monkeypatch.setattr(svc, "_run_job_fixture", flaky)
    _set_slots(2, "wait")
    run = run_orchestration()
    attempts = _assert_report_matches_attempts(run)

    failed = [a for a in attempts if a["status"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["detail"]["error"] == "fixture exploded"
    # The failed job still released the slot it held.
    assert failed[0]["detail"]["slot_state"] == "released_after_failure"
    assert "slot_index" in failed[0]["detail"]
    assert run["status"] == "partial"
    # fact_order_daily depended on the failed job and is recorded, not dropped.
    dep = [a for a in attempts if a["status"] == "skipped_dep"]
    assert len(dep) == 1 and "ingest_orders" in dep[0]["detail"]["reason"]
