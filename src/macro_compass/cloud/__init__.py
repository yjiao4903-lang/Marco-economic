"""V4 Cloud Mirror (cloud/sync).

Mirrors the migration-safe data + config to a remote so multiple PCs can share
one source of truth. Only ``config/``, ``data/raw/`` and ``data/canonical/``
are synced; every local artifact (``*.duckdb``, ``data/local/``, ``logs/``,
``.venv/``) stays machine-local. Each PC rebuilds its own DuckDB from the
canonical parquet it pulled (``scripts/rebuild_db.py``).

Backend is a Git private repository (git add/commit/pull/push wrapped in
``sync.py``, real ``git`` via subprocess). Failures surface as an explicit
status - never a silent fallback.
"""

from macro_compass.cloud.sync import (  # noqa: F401
    STATUS_CONFLICT,
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_NO_CHANGES,
    STATUS_OK,
    STATUS_SECRET_BLOCKED,
    SyncResult,
    build_manifest,
    git_available,
    sync_pull,
    sync_push,
    verify_manifest,
)

__all__ = [
    "STATUS_CONFLICT",
    "STATUS_DRY_RUN",
    "STATUS_FAILED",
    "STATUS_NO_CHANGES",
    "STATUS_OK",
    "STATUS_SECRET_BLOCKED",
    "SyncResult",
    "build_manifest",
    "git_available",
    "sync_pull",
    "sync_push",
    "verify_manifest",
]