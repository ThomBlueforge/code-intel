"""FastAPI application factory.

Wires the platform's capabilities (see :mod:`code_intel.api.routes`) under
``/api`` and, when a built browser UI is present, serves it as static files at
the site root. A background :class:`JobManager` lives on ``app.state.jobs`` so
long-running index/enrich/embed operations do not block requests.

The UI directory defaults to the packaged ``code_intel/webui`` folder and can be
overridden with ``CODE_INTEL_UI_DIR``. If no ``index.html`` is present (e.g. the
frontend has not been built yet), only the API is served.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from code_intel.api.jobs import JobManager
from code_intel.api.routes import router


def _ui_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.resolve()
    env = os.environ.get("CODE_INTEL_UI_DIR")
    if env and env.strip():
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent / "webui").resolve()


def create_app(ui_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Code Intelligence Platform", version="0.1.0")
    app.state.jobs = JobManager()
    app.include_router(router)

    directory = _ui_dir(ui_dir)
    if (directory / "index.html").is_file():
        # Mounted last so the "/api" routes above always take precedence.
        app.mount("/", StaticFiles(directory=str(directory), html=True), name="ui")

    return app


app = create_app()
