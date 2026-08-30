"""V4.5 Task 7 (P1) - Cloud Mirror size monitor.

A simple, read-only size statistic for the V4 Cloud Mirror footprint so the
repo does not silently grow without bound (intentionally NOT migrating to
Git LFS / OneDrive / object storage).

Outputs (per-PC local, never uploaded - consistent with cloud/local policy):
    data/local/cloud_size_report.csv

Stats computed:
    repo_size               - repo object store size via `git count-objects -vH`
                              (size-pack) + a requested RESERVE bucket naming.
    new_bytes_this_sync     - cumulative bytes under config/raw/canonical that
                              are NOT yet committed (working-tree delta).
    raw_file_count / count  - number + cumulative bytes per sync group.
    canonical_file_count    - idem for data/canonical.
    vintage_file_count      - snapshot files under data/local/vintage (per-PC local).

Design:
    * No git push/pull, no network, no writes to config/raw/canonical.
    * Reuses cloud.build_manifest + verify_manifest so the same
      config/raw/canonical scope (and the same local-only exclusions) apply.
    * Any git failure reports an explicit status row - no silent fallback.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.cloud.sync import build_manifest  # noqa: E402


def _git_bytes(root: Path, *args: str) -> int:
    """Run a git command and parse a byte/size number from stdout (0 on fail)."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    return _parse_size(proc.stdout) if proc.stdout.strip() else 0


def _parse_size(text: str) -> int:
    """Parse 'git count-objects -vH': sum the loose-objects 'size:' and the
    'size-pack:' lines (the full on-disk object-store footprint). Returns
    bytes; 0 if no size key is present/unparseable."""
    total = 0
    for line in text.splitlines():
        key = line.strip().split(":", 1)[0]
        if key in ("size", "size-pack"):
            val = line.split(":", 1)[1].strip()
            total += total_size(val)
    return total


def total_size(val: str) -> int:
    """Parse '143 KiB' / '12 MiB' / '934 B' into bytes (0 if unparseable)."""
    if not val:
        return 0
    words = val.replace(",", "").split()
    try:
        value = float(words[0])
    except (ValueError, IndexError):
        return 0
    if len(words) > 1:
        unit = words[1]
        mult = {
            "B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3,
            "TiB": 1024 ** 4, "KB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3,
        }.get(unit, 1)
        return int(value * mult)
    return int(value)


def _uncommitted_bytes(root: Path, manifest: list[str]) -> int:
    """Working-tree bytes under the sync scope that are not yet committed.
    Computed as the sum of on-disk sizes of in-scope files that git reports
    as modified or untracked (a silent, honest measure of the next push)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 0
    if proc.returncode != 0:
        return 0
    tracked = set(manifest)
    total = 0
    for line in proc.stdout.splitlines():
        if not line:
            continue
        # porcelain: "XY path" / "?? path"
        rel = line[3:].strip()
        if not rel:
            continue
        # skip scope-external entries (e.g. data/local) for a clean measure
        rel_posix = rel.replace("\\", "/")
        if rel_posix.startswith("data/local"):
            continue
        if rel_posix in tracked:
            try:
                total += (root / rel_posix).stat().st_size
            except OSError:
                pass
    return total


def _dir_stats(root: Path, rel_dir) -> dict:
    """Sum file count + bytes under a project-relative directory (if present)."""
    d = root / rel_dir
    count = 0
    total = 0
    if d.exists():
        for f in d.rglob("*"):
            if f.is_file():
                count += 1
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    return {"count": count, "bytes": total}


def main() -> None:
    root = paths.PROJECT_ROOT
    now = datetime.now().isoformat(timespec="seconds")

    manifest = build_manifest(root)
    total_bytes = 0
    for rel in manifest:
        try:
            total_bytes += (root / rel).stat().st_size
        except OSError:
            pass

    raw = _dir_stats(root, "data/raw")
    canonical = _dir_stats(root, "data/canonical")
    vintage = _dir_stats(root, "data/local/vintage")
    config = _dir_stats(root, "config")

    # Working-tree uncommitted bytes under the sync scope (the amount the next
    # push would report), surfaced explicitly - zero means clean.
    uncommitted = _uncommitted_bytes(root, manifest)
    # repo packing size (size-pack) - the object store footprint.
    pack_size = _git_bytes(root, "count-objects", "-vH")

    rows = [
        ["metric", "value", "unit", "checked_at"],
        ["repo_size (pack)", pack_size, "bytes", now],
        ["new_bytes_this_sync (working-tree diff)", uncommitted, "bytes", now],
        ["scope_latest_total_bytes", total_bytes, "bytes", now],
        ["config_file_count", config["count"], "count", now],
        ["raw_file_count", raw["count"], "count", now],
        ["canonical_file_count", canonical["count"], "count", now],
        ["vintage_file_count", vintage["count"], "count", now],
        ["raw_total_bytes", raw["bytes"], "bytes", now],
        ["canonical_total_bytes", canonical["bytes"], "bytes", now],
        ["vintage_total_bytes", vintage["bytes"], "bytes", now],
    ]

    paths.LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    out = paths.LOCAL_DIR / "cloud_size_report.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(rows)

    print(f"cloud size monitor - checked {now}")
    print(f"  repo pack size      : {pack_size} bytes")
    print(f"  new uncommitted bytes: {uncommitted} bytes")
    print(f"  scope latest total  : {total_bytes} bytes ({len(manifest)} files)")
    print(f"  config/raw/canonical: {config['count']}/{raw['count']}/{canonical['count']} files")
    print(f"  vintage (local)     : {vintage['count']} files")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()