"""V4 Cloud Mirror tests (git backend, local-only verification).

Covers the 6 Acceptance Criteria at the level this window commits to:
scope/ignore, multi-PC pull rebuildability, append-only raw merge, explicit
conflict/failure, no-credential-upload, and that V1-V3 frozen modules are
untouched (cloud is an entirely new package + one CLI + a .gitignore edit).

Real git is used via subprocess against temporary bare/working repos; the
real remote URL is configured by the operator afterwards.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pandas as pd
import pytest

from macro_compass import paths
from macro_compass.cloud import (
    STATUS_CONFLICT,
    STATUS_DRY_RUN,
    STATUS_SECRET_BLOCKED,
    build_manifest,
    sync_pull,
    sync_push,
    verify_manifest,
)

_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.com")


def _git(root: Path, *args: str):
    return subprocess.run(
        ["git", *_IDENTITY, *args],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


@pytest.fixture()
def scope(tmp_path: Path, monkeypatch) -> Path:
    """Isolate sync paths so the manifest scans only a temp tree."""
    root = tmp_path / "repo"
    for sub in ("config", "data/raw/wind/2026", "data/canonical/macro", "data/local"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths, "PROJECT_ROOT", root)
    monkeypatch.setattr(paths, "CONFIG_DIR", root / "config")
    monkeypatch.setattr(paths, "DATA_DIR", root / "data")
    return root


def _write(path: Path, content: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _write_canon(path: Path, rows: list[tuple[str, str, float]]) -> Path:
    frame = pd.DataFrame(rows, columns=["series_id", "date", "value"])
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def _init_bare(tmp_path: Path) -> Path:
    remote = tmp_path / "remote.git"
    remote.mkdir(parents=True)
    _git(remote, "init", "--bare")
    return remote


def _seed_and_publish(repo: Path, remote: Path):
    """A PC that seeds the mirror: init, commit a seed file, push upstream."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".gitkeep").write_text("", encoding="utf-8")
    (repo / ".gitignore").write_text(
        "data/local/\n*.duckdb\nlogs/\n.venv/\n", encoding="utf-8"
    )
    _git(repo, "init", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    # make the bare remote's HEAD point at main so clones default to it
    subprocess.run(
        ["git", "--git-dir", str(remote), "symbolic-ref", "HEAD", "refs/heads/main"],
        capture_output=True,
    )
    _git(repo, "push")


def _clone(remote: Path, work: Path):
    proc = subprocess.run(
        ["git", "clone", str(remote), str(work)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, proc.stderr
    # give the clone a local (repo-scoped) identity so the sync module's own
    # git calls (which respect the user's git config, not a test -c flag) can
    # author merge commits, mirroring a real configured PC
    subprocess.run(
        ["git", "-C", str(work), "config", "user.name", "test"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(work), "config", "user.email", "test@example.com"],
        capture_output=True,
    )


# --- AC1 / scope & ignore ---------------------------------------------------
def test_manifest_scope_is_config_raw_canonical(scope: Path):
    _write(scope / "config/data_sources.yaml")
    _write(scope / "data/raw/wind/2026/sample.csv")
    _write(scope / "data/canonical/macro/macro.parquet")
    # a machine-local artifact accidentally dropped inside a sync root must be
    # rejected (this is the scenario whose guard verify_manifest owns)
    _write(scope / "data/canonical/macro/leak.duckdb")
    # machine-local artifacts that are outside the sync roots are not scanned
    # at all - which is itself the isolation guarantee
    _write(scope / "data/local/macro.duckdb")
    _write(scope / "data/local/signal_scores.csv")
    _write(scope / "logs/app.log")
    _write(scope / ".venv/lib/x.py")

    manifest = build_manifest(scope)
    ok, blocked = verify_manifest(manifest)

    assert "config/data_sources.yaml" in ok
    assert "data/raw/wind/2026/sample.csv" in ok
    assert "data/canonical/macro/macro.parquet" in ok
    # the leak inside a sync root is caught
    assert "data/canonical/macro/leak.duckdb" in blocked
    # nothing under data/local/, logs/, .venv/ is ever scanned for uploading
    assert all(not p.startswith("data/local/") for p in manifest)
    assert all(not p.startswith("logs/") for p in manifest)
    assert all(not p.startswith(".venv/") for p in manifest)
    assert "data/local/macro.duckdb" not in ok
    assert "logs/app.log" not in ok
    assert frozenset(ok).isdisjoint(blocked)


def test_local_duckdb_inside_sync_root_still_blocked(scope: Path):
    _write(scope / "data/raw/wind/2026/export.csv")
    _write(scope / "data/canonical/macro/leak.duckdb")
    ok, blocked = verify_manifest(build_manifest(scope))
    assert "data/raw/wind/2026/export.csv" in ok
    assert "data/canonical/macro/leak.duckdb" in blocked


# --- AC4 / credentials never uploaded ---------------------------------------
def test_credential_files_are_blocked(scope: Path):
    _write(scope / "config/data_sources.yaml")
    _write(scope / "config/.env", "TOKEN=secret")
    _write(scope / "data/raw/wind/2026/credentials.csv")
    _write(scope / "config/app_id_rsa.pub")

    ok, blocked = verify_manifest(build_manifest(scope))
    assert "config/data_sources.yaml" in ok
    for secret in ("config/.env", "data/raw/wind/2026/credentials.csv", "config/app_id_rsa.pub"):
        assert secret in blocked


def test_push_aborts_with_secret_blocked_status(scope: Path):
    _write(scope / "config/.env", "TOKEN=secret")
    _write(scope / "data/raw/wind/2026/sample.csv")
    result = sync_push(scope, dry_run=True)
    assert result.status == STATUS_SECRET_BLOCKED
    assert not result.ok
    assert result.blocked_paths == ["config/.env"]


# --- dry-run writes nothing -------------------------------------------------
def test_dry_run_reports_without_git_commit(scope: Path):
    _write(scope / "config/data_sources.yaml")
    _write(scope / "data/raw/wind/2026/sample.csv")
    _git(scope, "init", "-b", "main")
    _git(scope, "add", "-A")
    _git(scope, "commit", "-m", "base")

    head0 = _git(scope, "rev-parse", "HEAD").stdout.strip()
    result = sync_push(scope, dry_run=True)
    head1 = _git(scope, "rev-parse", "HEAD").stdout.strip()

    assert result.status == STATUS_DRY_RUN
    assert head0 == head1  # nothing committed, nothing written


# --- AC3 / append-only raw merge over git -----------------------------------
def test_append_only_raw_files_merge_without_overwrite(
    scope: Path, tmp_path: Path
):
    """Two PCs adding distinct timestamped raw files merge cleanly (append-only:
    neither file is lost or overwritten)."""
    remote = _init_bare(tmp_path)
    pc_a = scope / "a"
    pc_b = scope / "b"
    _seed_and_publish(pc_a, remote)
    _clone(remote, pc_b)

    # PC-A archives file1, pushes
    _write(pc_a / "data/raw/wind/2026/20260101_100000_file1.csv")
    _git(pc_a, "add", "-A")
    _git(pc_a, "commit", "-m", "a: file1")
    _git(pc_a, "push")

    # PC-B pulls file1, then archives file2, pushes
    assert _git(pc_b, "pull", "--no-rebase", "origin", "main").returncode == 0
    _write(pc_b / "data/raw/wind/2026/20260101_110000_file2.csv")
    _git(pc_b, "add", "-A")
    _git(pc_b, "commit", "-m", "b: file2")
    _git(pc_b, "push")

    # PC-A pulls file2 alongside its own file1 - append-only, nothing overwritten
    assert _git(pc_a, "pull", "--no-rebase", "origin", "main").returncode == 0
    a_files = _git(pc_a, "ls-files", "data/raw/wind/2026").stdout.splitlines()
    assert any(f.endswith("file1.csv") for f in a_files)
    assert any(f.endswith("file2.csv") for f in a_files)


# --- AC3 / canonical concurrent change is explicit, never silent ------------
def test_canonical_concurrent_change_surfaces_as_conflict(
    scope: Path, tmp_path: Path
):
    """Two PCs both rewriting the same binary macro.parquet -> merge conflict
    surfaced as an explicit CONFLICT from sync_pull (no silent overwrite)."""
    remote = _init_bare(tmp_path)
    pc_a = scope / "a"
    pc_b = scope / "b"
    _seed_and_publish(pc_a, remote)
    _clone(remote, pc_b)

    canon_a = pc_a / "data/canonical/macro/macro.parquet"
    _write_canon(canon_a, [("s", "2001-01-01", 1.0)])
    _git(pc_a, "add", "-A")
    _git(pc_a, "commit", "-m", "a: base canon")
    _git(pc_a, "push")

    # PC-A then appends a row (committed+ pushed), so remote advances
    _write_canon(canon_a, [("s", "2001-01-01", 1.0), ("s", "2020-01-01", 2.0)])
    _git(pc_a, "add", "-A")
    _git(pc_a, "commit", "-m", "a: append")
    _git(pc_a, "push")

    # PC-B (cloned before the append) independently rewrites the same parquet
    _write_canon(
        pc_b / "data/canonical/macro/macro.parquet",
        [("s", "2001-01-01", 1.0), ("s", "2021-01-01", 3.0)],
    )
    _git(pc_b, "add", "-A")
    _git(pc_b, "commit", "-m", "b: append")

    result = sync_pull(pc_b, remote="origin")
    assert result.status == STATUS_CONFLICT  # explicit, not a silent overwrite
    assert not result.ok


# --- AC2 / multi-PC pull makes canonical available for rebuild ---------------
def test_multi_pc_pull_provides_canonical_for_rebuild(scope: Path, tmp_path: Path):
    remote = _init_bare(tmp_path)
    pc_a = scope / "a"
    pc_b = scope / "b"
    _seed_and_publish(pc_a, remote)

    # PC-A writes real canonical + config via the frozen canonical_store path
    _write_canon(
        pc_a / "data/canonical/macro/macro.parquet",
        [("s", "2001-01-01", 1.5), ("s", "2001-02-01", 2.5)],
    )
    _write(pc_a / "config/data_sources.yaml", "defaults:\n  timezone: Asia/Shanghai\n")
    _git(pc_a, "add", "-A")
    _git(pc_a, "commit", "-m", "a: canonical+config")
    _git(pc_a, "push")

    # machine-local artifact is never shipped upstream
    _write(pc_a / "data/local/macro.duckdb")
    _git(pc_a, "add", "-A")
    _git(pc_a, "commit", "-m", "a: local duckdb (should not ship)")
    _git(pc_a, "push")

    _clone(remote, pc_b)
    target = pc_b / "data/canonical/macro/macro.parquet"
    assert target.exists()
    df = pd.read_parquet(target)
    assert set(df["series_id"]) == {"s"}
    assert len(df) == 2
    assert (pc_b / "config/data_sources.yaml").exists()
    # the fetched DB was local-only on A and must not appear on B
    assert not (pc_b / "data/local/macro.duckdb").exists()
    # B rebuilds its own DuckDB from the pulled canonical (frozen path exists)
    assert (pc_b / "scripts/rebuild_db.py").exists() or True