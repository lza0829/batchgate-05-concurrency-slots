"""Base dependency check: upstream jobs must have a successful attempt in this orchestration."""

from __future__ import annotations

from typing import Any


def ready_by_upstream_success(
    depends_on: list[str],
    success_job_names: set[str],
) -> tuple[bool, str]:
    missing = [name for name in depends_on if name not in success_job_names]
    if missing:
        return False, f"upstream not success: {', '.join(missing)}"
    return True, "ok"


def topological_layers(jobs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group jobs into layers by declared depends_on names (best-effort for seed graphs)."""
    by_name = {j["name"]: j for j in jobs}
    remaining = set(by_name)
    done: set[str] = set()
    layers: list[list[dict[str, Any]]] = []
    while remaining:
        layer = []
        for name in sorted(remaining):
            deps = by_name[name]["depends_on"]
            if all(d in done for d in deps):
                layer.append(by_name[name])
        if not layer:
            # cycle or missing dep — dump rest as final layer for visibility
            layers.append([by_name[n] for n in sorted(remaining)])
            break
        layers.append(layer)
        for j in layer:
            remaining.remove(j["name"])
            done.add(j["name"])
    return layers
