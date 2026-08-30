"""V4 Cloud Mirror - Git-backed sync of config/raw/canonical (ARCHITECTURE §14).

Scope (mirror to cloud, multi-PC):
    config/  data/raw/  data/canonical/
Local-only (never uploaded, per-PC):
    *.duckdb  data/local/  data/inbox/  cache/  logs/  .venv/  .streamlit/

Semantics deliberately mirror the data layer:
- ``data/raw/wind/`` is append-only (timestamped archive files, never overwritten);
  Git tree merge of distinct new files resurfaces on every PC with no data loss.
- ``data/canonical/`` holds the merged source of truth; a true concurrent write
  to the same parquet from two PCs cannot be auto-merged by Git (binary) and is
  surfaced as an explicit CONFLICT status - never silently overwritten.
- Any revision history (GSCPI/BIS full_refresh vintage snapshots) lives under
  ``data/local/vintage/`` and is per-PC, so it is intentionally NOT uploaded.
- Failures return an explicit status (OK / NO_CHANGES / CONFLICT / FAILED /
  SECRET_BLOCKED); there is no silent fallback.
- Credentials are never uploaded: the sync manifest rejects secret-like file
  names and everything under the machine-local roots before any git call.

Status codes (namespaced to avoid colliding with the V1.2 update state machine):
    STATUS_OK                 sync committed and pushed/pulled successfully
    STATUS_NO_CHANGES         nothing to commit, nothing changed
    STATUS_DRY_RUN            manifest + verification reported, nothing written
    STATUS_CONFLICT           Git detected a merge conflict; needs manual action
    STATUS_SECRET_BLOCKED     manifest contained credential-like paths; aborted
    STATUS_FAILED             a git operation failed (no silent fallback)
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from macro_compass import paths
from macro_compass.logging import get_logger

logger = get_logger(__name__)

# --- status codes -----------------------------------------------------------
STATUS_OK = "SYNC_OK"
STATUS_NO_CHANGES = "SYNC_NO_CHANGES"
STATUS_DRY_RUN = "SYNC_DRY_RUN"
STATUS_CONFLICT = "SYNC_CONFLICT"
STATUS_SECRET_BLOCKED = "SYNC_SECRET_BLOCKED"
STATUS_FAILED = "SYNC_FAILED"

# --- sync scope -------------------------------------------------------------
# Roots that are mirrored to the cloud. Each is resolved against the project
# root at call time via ``paths`` so tests can monkeypatch them.
SYNC_GROUPS = {
    "config": "config",
    "raw": "raw",
    "canonical": "canonical",
}


def _sync_roots() -> tuple[Path, str]:
    """Return (project_root, comma-joined relative sync paths)."""
    root = paths.PROJECT_ROOT
    rel = tuple(sorted({f"{paths.CONFIG_DIR.name}", "data", "data/raw", "data/canonical"}))
    # git add accepts paths under the project root; use the directory names.
    return root, f"{paths.CONFIG_DIR.name} data/raw data/canonical"


# Machine-local paths that must NEVER be uploaded, expressed as directories
# relative to the project root plus file-suffix rules. This is the hard guard;
# .gitignore is the secondary guard.
_LOCAL_ONLY_DIR_REL = (
    "data/local",
    "data/inbox",
    "logs",
    ".venv",
    ".streamlit",
    "cache",
    "__pycache__",
    ".pytest_cache",
    ".git",
)
_LOCAL_ONLY_SUFFIXES = (".duckdb", ".duckdb.wal", ".pyc", ".egg-info")
_SECRET_NAME_RE = re.compile(
    r"(credentials|secret|\.env(\.local)?$|\.key$|\.pem$|\.p12$"
    r"|id_rsa|api[_-]?key|access[_-]?token|password)", re.IGNORECASE
)


@dataclass
class SyncResult:
    """Outcome of a sync run. Mirrors the V1.2 update-report shape.

    ``status`` is one of the STATUS_* codes above. ``manifest`` lists every
    file that would/was uploaded (relative to project root). ``blocked_paths``
    lists any local-only or credential-like path that was rejected.
    """

    status: str
    manifest: list[str] = field(default_factory=list)
    committed: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    message: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in (STATUS_OK, STATUS_NO_CHANGES)

    def summary(self) -> str:
        lines = [
            f"cloud sync status : {self.status}",
            f"files in scope    : {len(self.manifest)}",
        ]
        if self.blocked_paths:
            lines.append(f"blocked from upload: {len(self.blocked_paths)}")
        if self.message:
            lines.append(f"detail            : {self.message}")
        for err in self.errors:
            lines.append(f"error             : {err}")
        return "\n".join(lines)


# --- helpers ----------------------------------------------------------------
def _rel_path(root: Path, file_path: Path) -> str:
    return file_path.relative_to(root).as_posix()


def _is_local_only(rel: str) -> bool:
    """True if ``rel`` (posix, project-root-relative) is a machine-local path."""
    if any(rel.endswith(suf) for suf in _LOCAL_ONLY_SUFFIXES):
        return True
    first = rel.split("/")[0]
    if first in _LOCAL_ONLY_DIR_REL:
        return True
    # nesting like data/local/vintage/...
    return any(rel.startswith(f"{d}/") for d in _LOCAL_ONLY_DIR_REL)


def _is_secret(name: str) -> bool:
    """True if the file name looks like a credential artifact. Name-level guard;
    the real project has no secrets under config/, but cloud pushes must stay
    provably clean even if a key file is dropped nearby."""
    base = Path(name).name
    return bool(_SECRET_NAME_RE.search(base))


# --- manifest & verification ------------------------------------------------
def build_manifest(root: Path | None = None) -> list[str]:
    """Return every file under the sync roots (config/raw/canonical) as
    project-root-relative posix paths. Machine-local files anywhere under a
    sync root are also listed here so ``verify_manifest`` can reject them."""
    root = root or paths.PROJECT_ROOT
    groups = [
        paths.CONFIG_DIR,
        paths.DATA_DIR / "raw",
        paths.DATA_DIR / "canonical",
    ]
    found: list[str] = []
    for group_dir in groups:
        if not group_dir.exists():
            continue
        for file_path in sorted(group_dir.rglob("*")):
            if file_path.is_file():
                found.append(_rel_path(root, file_path))
    return found


def verify_manifest(manifest: list[str]) -> tuple[list[str], list[str]]:
    """Split a manifest into (upload_ok, blocked).

    ``blocked`` contains machine-local artifacts (duckdb / data/local / logs /
    .venv / cache) and credential-like file names. Anything blocked here is
    never handed to git - this is the no-upload guarantee independent of
    .gitignore.
    """
    ok: list[str] = []
    blocked: list[str] = []
    for rel in manifest:
        if _is_local_only(rel):
            blocked.append(rel)
        elif _is_secret(rel):
            blocked.append(rel)
        else:
            ok.append(rel)
    return ok, blocked


# --- git backend -----------------------------------------------------------
@dataclass
class _GitOp:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = -1


def _git(root: Path, *args: str) -> _GitOp:
    cmd = ["git", *args]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except FileNotFoundError:
        return _GitOp(False, "", "git executable not found", -1)
    except subprocess.TimeoutExpired:
        return _GitOp(False, "", "git command timed out", -1)
    return _GitOp(
        ok=proc.returncode == 0,
        stdout=proc.stdout.strip(),
        stderr=proc.stderr.strip(),
        returncode=proc.returncode,
    )


def git_available(root: Path | None = None) -> bool:
    root = root or paths.PROJECT_ROOT
    op = _git(root, "--version")
    if not op.ok:
        logger.warning("cloud sync requires git: %s", op.stderr)
    return op.ok


def _current_branch(root: Path) -> str:
    op = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    return op.stdout if op.ok else "HEAD"


def _has_local_changes(root: Path, *scope: str) -> bool:
    """True if there is anything staged or unstaged under scope."""
    if scope:
        op = _git(root, "status", "--porcelain", "--", *scope)
    else:
        op = _git(root, "status", "--porcelain")
    return op.ok and bool(op.stdout.strip())


# --- orchestration ---------------------------------------------------------
def sync_push(
    root: Path | None = None,
    dry_run: bool = False,
    remote: str = "origin",
    branch: str | None = None,
    message: str | None = None,
    skip_network: bool = False,
) -> SyncResult:
    """Commit the in-scope files and push to ``remote``.

    Flow (no silent fallback):
      1. build + verify manifest -> SECRET_BLOCKED stops on any local-only or
         credential path;
      2. ``git add`` the sync scope;
      3. if there are staged changes, commit;
      4. if the remote has new commits, pull (merge) - a conflict is surfaced
         as CONFLICT and the caller must resolve it manually;
      5. push; any git failure -> FAILED.

    ``skip_network=True`` (used by tests) exercises commit/manifest/verify
    without touching pull/push.
    """
    root = root or paths.PROJECT_ROOT
    _, scope_str = _sync_roots()

    manifest = build_manifest(root)
    upload_ok, blocked = verify_manifest(manifest)
    if blocked:
        return SyncResult(
            status=STATUS_SECRET_BLOCKED,
            manifest=manifest,
            blocked_paths=blocked,
            message="refusing to push: machine-local or credential-like files in scope; "
            "fix .gitignore / move the files before retrying.",
            errors=[f"blocked: {b}" for b in blocked],
        )

    if dry_run:
        return SyncResult(
            status=STATUS_DRY_RUN,
            manifest=upload_ok,
            message=f"dry run: {len(upload_ok)} files would be uploaded to {remote}",
        )

    if not git_available(root):
        return SyncResult(
            status=STATUS_FAILED,
            manifest=upload_ok,
            errors=["git executable not available"],
            message="cannot sync without git",
        )

    branch = branch or _current_branch(root)

    # 2. stage scope
    stage = _git(root, "add", "--", *scope_str.split())
    if not stage.ok:
        return SyncResult(
            status=STATUS_FAILED,
            manifest=upload_ok,
            errors=[f"git add failed: {stage.stderr}"],
            message="staging in-scope files failed",
        )

    committed: list[str] = []
    if _has_local_changes(root, *scope_str.split()):
        msg = message or f"V4 cloud mirror: sync {datetime.now():%Y-%m-%d %H:%M:%S}"
        commit = _git(root, "commit", "-m", msg)
        if not commit.ok:
            return SyncResult(
                status=STATUS_FAILED,
                manifest=upload_ok,
                errors=[f"git commit failed: {commit.stderr}"],
                message="commit failed; check git identity / hooks",
            )
        committed = upload_ok

    if skip_network:
        return SyncResult(
            status=STATUS_OK if committed else STATUS_NO_CHANGES,
            manifest=upload_ok,
            committed=committed,
            message="local commit done; network pull/push skipped (test mode)",
        )

    # 4. pull (merge) remote changes so we don't clobber another PC
    pull = _git(root, "pull", "--no-rebase", remote, branch)
    if not pull.ok:
        if "CONFLICT" in pull.stdout or "CONFLICT" in pull.stderr or pull.returncode == 1:
            return SyncResult(
                status=STATUS_CONFLICT,
                manifest=upload_ok,
                committed=committed,
                errors=[f"git pull conflict: {pull.stderr or pull.stdout}"],
                message="merge conflict on pull - resolve manually, then re-run sync",
            )
        return SyncResult(
            status=STATUS_FAILED,
            manifest=upload_ok,
            committed=committed,
            errors=[f"git pull failed: {pull.stderr or pull.stdout}"],
            message="pull from remote failed (no silent fallback)",
        )

    # 5. push
    push = _git(root, "push", remote, branch)
    if not push.ok:
        return SyncResult(
            status=STATUS_FAILED,
            manifest=upload_ok,
            committed=committed,
            errors=[f"git push failed: {push.stderr or push.stdout}"],
            message="push to remote failed (no silent fallback)",
        )

    status = STATUS_OK if (committed or "up to date" not in push.stdout) else STATUS_NO_CHANGES
    return SyncResult(
        status=status,
        manifest=upload_ok,
        committed=committed,
        message=f"pushed {branch} to {remote}",
    )


def sync_pull(
    root: Path | None = None,
    dry_run: bool = False,
    remote: str = "origin",
    branch: str | None = None,
) -> SyncResult:
    """Pull the mirrored config/raw/canonical down from ``remote``.

    This is the multi-PC side of the mirror: after a successful pull the user
    runs ``scripts/rebuild_db.py`` to rebuild the per-PC DuckDB. A merge
    conflict is surfaced as CONFLICT (assert preserved prior to destroying the
    working tree). No local machine artifact is ever written by a pull.
    """
    root = root or paths.PROJECT_ROOT
    _, scope_str = _sync_roots()

    manifest = build_manifest(root)
    upload_ok, blocked = verify_manifest(manifest)

    if dry_run:
        status = STATUS_DRY_RUN
        return SyncResult(
            status=status,
            manifest=upload_ok,
            blocked_paths=blocked,
            message=f"dry run: would pull {remote} into this checkout",
        )

    if not git_available(root):
        return SyncResult(status=STATUS_FAILED, errors=["git executable not available"])

    branch = branch or _current_branch(root)

    # Refuse to clobber local-only machine artifacts on a hard conflict that
    # would otherwise destroy the working tree; surface it explicitly instead.
    if _has_local_changes(root):
        dirty = _git(root, "status", "--porcelain").stdout.splitlines()
        in_scope = [ln for ln in dirty if not any(b in ln for b in blocked)]
        if in_scope:
            return SyncResult(
                status=STATUS_FAILED,
                manifest=upload_ok,
                errors=[f"untracked/modified in-scope files: {in_scope}"],
                message="commit or stash in-scope changes before pulling (no silent "
                "overwrite of local work)",
            )

    pull = _git(root, "pull", "--no-rebase", remote, branch)
    if not pull.ok:
        if "CONFLICT" in pull.stdout or "CONFLICT" in pull.stderr or pull.returncode == 1:
            return SyncResult(
                status=STATUS_CONFLICT,
                manifest=upload_ok,
                errors=[f"git pull conflict: {pull.stderr or pull.stdout}"],
                message="merge conflict on pull - resolve manually, then re-run sync",
            )
        return SyncResult(
            status=STATUS_FAILED,
            manifest=upload_ok,
            errors=[f"git pull failed: {pull.stderr or pull.stdout}"],
            message="pull from remote failed (no silent fallback)",
        )

    return SyncResult(
        status=STATUS_OK,
        manifest=upload_ok,
        message=f"pulled {branch} from {remote}; run rebuild_db.py to rebuild DuckDB",
    )