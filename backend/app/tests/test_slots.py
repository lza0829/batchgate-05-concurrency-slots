import threading
import time

import pytest

from app.engines.slots import (
    DISPOSITION_ACQUIRED,
    DISPOSITION_SKIPPED_SLOT,
    DISPOSITION_WAITED,
    normalize_limit,
    normalize_policy,
    plan_layer,
    run_layer,
    SlotPool,
)


def test_plan_layer_within_limit():
    decisions = plan_layer(2, 2, "wait")
    assert [d.disposition for d in decisions] == [DISPOSITION_ACQUIRED] * 2
    assert all(d.admitted for d in decisions)


def test_plan_layer_wait_policy():
    decisions = plan_layer(4, 2, "wait")
    assert [d.disposition for d in decisions] == [
        DISPOSITION_ACQUIRED,
        DISPOSITION_ACQUIRED,
        DISPOSITION_WAITED,
        DISPOSITION_WAITED,
    ]
    assert [d.queue_position for d in decisions] == [0, 1, 2, 3]
    assert decisions[2].waited and decisions[2].admitted


def test_plan_layer_skip_policy():
    decisions = plan_layer(3, 1, "skip")
    assert decisions[0].disposition == DISPOSITION_ACQUIRED
    assert [d.disposition for d in decisions[1:]] == [DISPOSITION_SKIPPED_SLOT] * 2
    assert not any(d.admitted for d in decisions[1:])


def test_plan_layer_empty():
    assert plan_layer(0, 2, "wait") == []


def test_normalize_limit_and_policy():
    assert normalize_limit("3") == 3
    assert normalize_limit(1) == 1
    with pytest.raises(ValueError):
        normalize_limit(0)
    with pytest.raises(ValueError):
        normalize_limit("abc")
    assert normalize_policy("WAIT") == "wait"
    with pytest.raises(ValueError):
        normalize_policy("retry")


def test_run_layer_enforces_wave_limit():
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}

    def work(job):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return {"ok": True, "job": job["name"]}

    jobs = [{"name": f"j{i}"} for i in range(5)]
    outcomes = run_layer(jobs, limit=2, policy="wait", run_job=work)
    assert state["peak"] <= 2
    assert [o.job["name"] for o in outcomes] == [j["name"] for j in jobs]
    assert all(o.result == {"ok": True, "job": o.job["name"]} for o in outcomes)
    assert all(o.error is None for o in outcomes)


def test_run_layer_skip_policy_does_not_execute():
    calls = []
    jobs = [{"name": f"j{i}"} for i in range(4)]
    outcomes = run_layer(
        jobs, limit=1, policy="skip", run_job=lambda j: calls.append(j) or {"ok": True}
    )
    assert calls == [jobs[0]]
    assert outcomes[0].result == {"ok": True}
    assert all(o.result is None and o.error is None for o in outcomes[1:])


def test_run_layer_captures_errors():
    def boom(job):
        raise RuntimeError(f"bad {job['name']}")

    jobs = [{"name": "j0"}, {"name": "j1"}]
    outcomes = run_layer(jobs, limit=2, policy="wait", run_job=boom)
    assert [o.error for o in outcomes] == ["bad j0", "bad j1"]
    assert all(o.result is None for o in outcomes)


def test_run_layer_admits_in_ticket_order():
    order = []
    lock = threading.Lock()

    def work(job):
        with lock:
            order.append(job["name"])
        return {"ok": True}

    jobs = [{"name": f"j{i}"} for i in range(4)]
    outcomes = run_layer(jobs, limit=2, policy="wait", run_job=work)
    # Admission order is positional; slot 0 is reused for the second wave.
    assert order == ["j0", "j1", "j2", "j3"]
    assert [o.lease.ticket for o in outcomes] == [0, 1, 2, 3]
    assert [o.lease.slot_index for o in outcomes] == [0, 1, 0, 1]
    assert all(o.lease.released_at >= o.lease.acquired_at for o in outcomes)


def test_slot_pool_release_frees_capacity():
    pool = SlotPool(1)
    first = pool.acquire(0)
    assert pool.peak_active == 1
    pool.release(first)
    second = pool.acquire(1)
    assert second == 0
    pool.release(second)
    assert pool.peak_active == 1
