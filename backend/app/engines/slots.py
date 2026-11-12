"""Concurrency-slot planning and layer execution.

A topological layer runs its jobs against a real bounded slot pool.  Every
dependency-ready job in a layer gets a deterministic slot decision based on its
position in the layer:

* ``acquired``               – job is within the first ``limit`` positions and
                               takes a slot without queuing.
* ``waited_then_acquired``   – job is past the first ``limit`` positions and only
                               starts after an earlier job releases its slot
                               (policy ``wait``).
* ``skipped_slot``           – job is past the first ``limit`` positions and is
                               dropped instead of queued (policy ``skip``).

Decisions are positional, not based on wall-clock timing, so the audit trail is
stable across runs and machines.  Jobs really do execute concurrently; admission
is FIFO by ticket so the slot a job held is reproducible.  Every execution takes
a lease from :class:`SlotPool` and records which slot index it held, its ticket,
when it acquired/released it and how long it waited, so occupancy and release are
auditable after the fact.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from concurrent.futures import ThreadPoolExecutor

SLOT_POLICY_WAIT = "wait"
SLOT_POLICY_SKIP = "skip"
SLOT_POLICIES = (SLOT_POLICY_WAIT, SLOT_POLICY_SKIP)
DEFAULT_SLOT_POLICY = SLOT_POLICY_WAIT

MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 20
DEFAULT_CONCURRENCY = 2

DISPOSITION_ACQUIRED = "acquired"
DISPOSITION_WAITED = "waited_then_acquired"
DISPOSITION_SKIPPED_SLOT = "skipped_slot"


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def normalize_limit(value: int | str | None) -> int:
    """Parse/clamp a configured concurrency limit, raising on non-numeric input."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("concurrency limit must be an integer")
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("concurrency limit must be an integer") from exc
    if parsed < MIN_CONCURRENCY or parsed > MAX_CONCURRENCY:
        raise ValueError(
            f"concurrency limit must be between {MIN_CONCURRENCY} and {MAX_CONCURRENCY}"
        )
    return parsed


def normalize_policy(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text not in SLOT_POLICIES:
        raise ValueError(f"slot policy must be one of: {', '.join(SLOT_POLICIES)}")
    return text


class SlotPool:
    """Bounded pool of numbered slots with FIFO admission and release bookkeeping.

    Tickets are handed out in layer order.  A ticket may take a slot only once all
    lower tickets have taken theirs, so admission order (and therefore the slot
    each job held) is deterministic even though jobs run concurrently.
    """

    def __init__(self, limit: int) -> None:
        self.limit = normalize_limit(limit)
        self._cond = threading.Condition()
        self._free = list(range(self.limit))
        self._next_ticket = 0
        self._active = 0
        self.peak_active = 0

    def acquire(self, ticket: int, timeout: float | None = None) -> int:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._cond:
            while ticket != self._next_ticket or not self._free:
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("timed out waiting for a concurrency slot")
                self._cond.wait(remaining)
            index = self._free.pop(0)
            self._next_ticket += 1
            self._active += 1
            self.peak_active = max(self.peak_active, self._active)
            self._cond.notify_all()
            return index

    def release(self, index: int) -> None:
        with self._cond:
            self._free.append(index)
            self._active -= 1
            self._cond.notify_all()


@dataclass(frozen=True)
class SlotLease:
    ticket: int
    slot_index: int
    acquired_at: str
    released_at: str
    held_seconds: float
    waited_seconds: float

    def as_detail(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket,
            "slot_index": self.slot_index,
            "acquired_at": self.acquired_at,
            "released_at": self.released_at,
            "held_seconds": round(self.held_seconds, 3),
            "waited_seconds": round(self.waited_seconds, 3),
        }


@dataclass(frozen=True)
class SlotDecision:
    """Planned positional decision for one job in a layer."""

    limit: int
    policy: str
    disposition: str
    queue_position: int
    waited: bool

    @property
    def admitted(self) -> bool:
        return self.disposition in (DISPOSITION_ACQUIRED, DISPOSITION_WAITED)

    @property
    def wave(self) -> int:
        """Planned wave index (queue_position // limit); skipped jobs get -1."""
        if not self.admitted:
            return -1
        return self.queue_position // self.limit

    def as_detail(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "policy": self.policy,
            "disposition": self.disposition,
            "queue_position": self.queue_position,
            "planned_wave": self.wave,
            "planned_waited": self.waited,
        }


@dataclass(frozen=True)
class LayerOutcome:
    job: dict[str, Any]
    decision: SlotDecision
    result: dict[str, Any] | None
    error: str | None
    lease: SlotLease | None = None

    def as_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = dict(self.decision.as_detail())
        if self.lease is not None:
            detail.update(self.lease.as_detail())
        return detail


def plan_layer(layer_size: int, limit: int, policy: str) -> list[SlotDecision]:
    """Deterministically assign a slot decision to every job position in a layer."""
    if layer_size < 0:
        raise ValueError("layer_size must be >= 0")
    limit = normalize_limit(limit)
    policy = normalize_policy(policy)
    decisions: list[SlotDecision] = []
    for position in range(layer_size):
        if position < limit:
            decisions.append(
                SlotDecision(limit, policy, DISPOSITION_ACQUIRED, position, False)
            )
        elif policy == SLOT_POLICY_SKIP:
            decisions.append(
                SlotDecision(limit, policy, DISPOSITION_SKIPPED_SLOT, position, False)
            )
        else:
            decisions.append(
                SlotDecision(limit, policy, DISPOSITION_WAITED, position, True)
            )
    return decisions


def run_layer(
    jobs: list[dict[str, Any]],
    *,
    limit: int,
    policy: str,
    run_job: Callable[[dict[str, Any]], dict[str, Any]],
    pool: SlotPool | None = None,
) -> list[LayerOutcome]:
    """Execute a layer against the slot pool, returning one outcome per job.

    Pass ``pool`` to observe occupancy afterwards (``pool.peak_active``); when
    omitted a private pool is created for this layer.
    """
    decisions = plan_layer(len(jobs), limit, policy)
    results: list[dict[str, Any] | None] = [None] * len(jobs)
    errors: list[str | None] = [None] * len(jobs)
    leases: list[SlotLease | None] = [None] * len(jobs)

    pool = pool or SlotPool(limit)
    admitted = [i for i, d in enumerate(decisions) if d.admitted]

    # Submit every admitted job at once; the slot pool (not the executor) is what
    # bounds concurrency.  Jobs beyond the first ``limit`` therefore genuinely
    # block on the pool and record the time they waited for a slot.
    if admitted:
        with ThreadPoolExecutor(max_workers=len(admitted)) as executor:
            futures = {
                index: executor.submit(
                    _run_with_slot, pool, run_job, jobs[index], ticket
                )
                for ticket, index in enumerate(admitted)
            }
            for index, future in futures.items():
                outcome = future.result()
                results[index] = outcome["result"]
                errors[index] = outcome["error"]
                leases[index] = outcome["lease"]

    return [
        LayerOutcome(
            job=jobs[i],
            decision=decisions[i],
            result=results[i],
            error=errors[i],
            lease=leases[i],
        )
        for i in range(len(jobs))
    ]


def _run_with_slot(
    pool: SlotPool,
    run_job: Callable[[dict[str, Any]], dict[str, Any]],
    job: dict[str, Any],
    ticket: int,
) -> dict[str, Any]:
    wait_started = time.monotonic()
    try:
        slot_index = pool.acquire(ticket)
    except Exception as exc:  # noqa: BLE001
        return {"result": None, "error": str(exc), "lease": None}
    acquired_at = _iso_now()
    acquired_monotonic = time.monotonic()
    result: dict[str, Any] | None = None
    error: str | None = None
    try:
        result = run_job(job)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
    finally:
        released_at = _iso_now()
        held = time.monotonic() - acquired_monotonic
        waited = acquired_monotonic - wait_started
        pool.release(slot_index)
    return {
        "result": result,
        "error": error,
        "lease": SlotLease(
            ticket=ticket,
            slot_index=slot_index,
            acquired_at=acquired_at,
            released_at=released_at,
            held_seconds=held,
            waited_seconds=waited,
        ),
    }
