"""Preview and, only with ``--apply``, promote the two D2/D4 candidates."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.d2_d4_promotion import (  # noqa: E402
    PromotionError,
    _load_pbc_reported,
    apply_promotion,
    build_promotion_plan,
    write_report,
)
from macro_compass.storage.canonical_store import read_canonical  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the validated historical replacement")
    parser.add_argument("--canonical", type=Path, default=paths.MACRO_PARQUET)
    parser.add_argument("--db", type=Path, default=paths.DUCKDB_PATH)
    parser.add_argument(
        "--pbc-reported",
        type=Path,
        default=paths.LOCAL_DIR / "pbc_reported_flow_candidates_20260831.csv",
    )
    parser.add_argument("--backup-dir", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)

    report_path = args.report or ROOT / "outputs" / "d2_d4_promotion_report.json"
    try:
        canonical = pd.read_parquet(args.canonical)
        pbc = _load_pbc_reported(args.pbc_reported)
        plan = build_promotion_plan(canonical, pbc)
        plan.report["mode"] = "apply" if args.apply else "dry-run"
        if args.apply:
            registry = load_indicator_config(paths.INDICATORS_YAML)
            backup = args.backup_dir or ROOT / "data" / "local" / (
                "promotion_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
            )
            plan.report["apply_result"] = apply_promotion(
                plan, args.canonical, args.db, registry, backup
            )
        write_report(plan.report, report_path)
        print(f"Promotion {plan.report['mode']}: {plan.report['status']}")
        print(f"Report: {report_path}")
        return 0
    except (PromotionError, OSError, ValueError) as exc:
        print(f"Promotion BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
