"""In-process background jobs for long-running operations.

Indexing, enrichment, and embedding can be slow, so the HTTP API runs them as
background jobs: the browser kicks one off, receives a job id, and polls for a
progress snapshot instead of blocking on the request.

Jobs run in daemon threads inside the server process. This is a single-user,
localhost tool, so there is no external queue or persistence — a restart clears
the job list. Each job exposes a status, a progress snapshot, and (on success) a
JSON-serialisable ``result``, or an ``error`` string on failure.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from code_intel.models import utc_now_iso

# A job body receives an ``update`` callback: update(done, total, message).
# ``total`` is ``None`` while the size of the work is not yet known.
ProgressUpdate = Callable[[int, "int | None", str], None]
JobBody = Callable[[ProgressUpdate], dict[str, Any]]


@dataclass
class Job:
    """Mutable state for one background operation (guarded by JobManager's lock)."""

    id: str
    kind: str
    status: str = "pending"  # pending | running | done | error
    done: int = 0
    total: int | None = None
    message: str = ""
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "progress": {"done": self.done, "total": self.total, "message": self.message},
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobManager:
    """Submits job bodies to daemon threads and tracks their progress."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def submit(self, kind: str, body: JobBody) -> Job:
        job = Job(id=str(uuid.uuid4()), kind=kind)
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job, body), daemon=True)
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def _run(self, job: Job, body: JobBody) -> None:
        with self._lock:
            job.status = "running"
            job.updated_at = utc_now_iso()

        def update(done: int, total: int | None, message: str) -> None:
            with self._lock:
                job.done = done
                job.total = total
                job.message = message
                job.updated_at = utc_now_iso()

        try:
            result = body(update)
        except Exception as exc:  # job boundary: surface any failure to the client
            with self._lock:
                job.status = "error"
                job.error = f"{type(exc).__name__}: {exc}"
                job.updated_at = utc_now_iso()
            return
        with self._lock:
            job.status = "done"
            job.result = result
            job.updated_at = utc_now_iso()
