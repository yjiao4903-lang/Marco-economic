"""Export Marco's narrow v1 snapshots for the cross-asset decision engine.

Usage (PowerShell):
    python scripts/export_cross_asset_snapshot.py `
      --today 2026-09-02 `
      --output-dir artifacts/integration/latest

The command is read-only with respect to canonical data and DuckDB. It runs the
existing Macro, Regime, Structural and Fundamental Asset engines, deliberately
omitting Market Confirmation from the fundamental export.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from macro_compass.integration import export_live_repository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--today",
        required=True,
        help="fixed research as-of date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/integration/latest",
        help="directory for the four integration JSON files",
    )
    parser.add_argument(
        "--allow-synthetic",
        action="store_true",
        help="test-only: include synthetic fixture rows; production default excludes them",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir

    paths = export_live_repository(
        today=args.today,
        output_dir=output_dir,
        project_root=PROJECT_ROOT,
        allow_synthetic=args.allow_synthetic,
    )
    for name in (
        "macro_snapshot.json",
        "structural_snapshot.json",
        "fundamental_asset_view.json",
        "integration_manifest.json",
    ):
        print(f"{name}: {paths[name]}")


if __name__ == "__main__":
    main()
