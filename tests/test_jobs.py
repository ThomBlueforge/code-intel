"""Tests for the in-process background job manager (U1)."""

from __future__ import annotations

import time

from code_intel.api.jobs import Job, JobManager, ProgressUpdate


def _wait(manager: JobManager, job_id: str) -> Job:
    for _ in range(200):
        job = manager.get(job_id)
        if job is not None and job.status in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def test_job_success_reports_result_and_progress() -> None:
    manager = JobManager()

    def body(update: ProgressUpdate) -> dict[str, object]:
        update(1, 2, "halfway")
        return {"ok": True}

    submitted = manager.submit("test", body)
    done = _wait(manager, submitted.id)
    assert done.status == "done"
    assert done.result == {"ok": True}
    assert done.done == 1
    assert done.total == 2
    assert done.message == "halfway"


def test_job_failure_records_error() -> None:
    manager = JobManager()

    def body(update: ProgressUpdate) -> dict[str, object]:
        raise ValueError("boom")

    submitted = manager.submit("test", body)
    done = _wait(manager, submitted.id)
    assert done.status == "error"
    assert done.error is not None
    assert "boom" in done.error


def test_get_unknown_job_is_none() -> None:
    assert JobManager().get("nope") is None
