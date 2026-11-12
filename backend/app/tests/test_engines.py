from pathlib import Path

from app.engines.dependency import ready_by_upstream_success, topological_layers
from app.engines.job_runner import load_fixture, run_fixture_job


def test_ready_by_upstream_success():
    ok, _ = ready_by_upstream_success(["a", "b"], {"a", "b"})
    assert ok
    ok, reason = ready_by_upstream_success(["a", "b"], {"a"})
    assert not ok
    assert "b" in reason


def test_topological_layers():
    jobs = [
        {"name": "a", "depends_on": []},
        {"name": "b", "depends_on": []},
        {"name": "c", "depends_on": ["a", "b"]},
    ]
    layers = topological_layers(jobs)
    assert {j["name"] for j in layers[0]} == {"a", "b"}
    assert [j["name"] for j in layers[1]] == ["c"]


def test_run_fixture(tmp_path: Path):
    p = tmp_path / "x.json"
    p.write_text('{"watermark_ts":"2026-01-01T00:00:00Z","rows":[{"id":1}]}', encoding="utf-8")
    out = run_fixture_job(p)
    assert out["ok"] and out["artifact_rows"] == 1
    assert load_fixture(p)["watermark_ts"].startswith("2026")
