"""V4 Cloud Mirror sync entry point (ARCHITECTURE §14).

Mirrors the migration-safe data + config to a Git remote so multiple PCs share
one source of truth. Only ``config/``, ``data/raw/`` and ``data/canonical/``
are synced; machine-local artifacts (``*.duckdb``, ``data/local/``, ``logs/``,
``.venv/``) are never uploaded. After pulling on a new PC, rebuild the local
DuckDB with ``scripts/rebuild_db.py``.

Flow (no silent fallback):
    push   verify scope (rejects local-only/credential files) -> git add ->
           commit -> git pull (merge; conflicting -> CONFLICT) -> git push
    pull   verify scope -> git pull (merge) -> hint to run rebuild_db.py

Examples:
    python scripts/cloud_sync.py --dry-run        # print what would sync
    python scripts/cloud_sync.py                  # commit + push to origin
    python scripts/cloud_sync.py --pull           # pull latest, then rebuild_db
    python scripts/cloud_sync.py --remote mine    # non-default remote
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass.cloud import sync_pull, sync_push  # noqa: E402
from macro_compass.logging import setup_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pull",
        action="store_true",
        help="pull latest mirrored config/raw/canonical from remote "
        "(then rebuild DuckDB with scripts/rebuild_db.py)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="build + verify the manifest and report, but write/upload nothing",
    )
    parser.add_argument(
        "--remote",
        default="origin",
        help="git remote name (default: origin)",
    )
    parser.add_argument(
        "--message",
        default=None,
        help="commit message (default: auto timestamp)",
    )
    args = parser.parse_args(argv)

    setup_logging()
    if args.pull:
        result = sync_pull(dry_run=args.dry_run, remote=args.remote)
    else:
        result = sync_push(dry_run=args.dry_run, remote=args.remote, message=args.message)

    print(result.summary())
    # dry-run is a legitimate read-only preview, not a failure
    if result.status == "SYNC_DRY_RUN":
        return 0
    if result.status == "SYNC_SECRET_BLOCKED":
        print("refusing to upload machine-local / credential files - see blocked list above.")
        return 3
    if result.status == "SYNC_CONFLICT":
        print("merge conflict detected - resolve manually, then re-run this script.")
        return 2
    if not result.ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())