"""Apply the verified PBC-reported 2026-04..07 tail to two production series.

This is deliberately narrower than the historical D2/D4 promotion script:
it never touches the Wind history through 2026-03, candidate series IDs,
GOLD/S3/USD data, or configuration routes.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "src"))

from macro_compass import paths  # noqa: E402
from macro_compass.config import load_indicator_config  # noqa: E402
from macro_compass.storage.duckdb_store import rebuild_duckdb_from_canonical  # noqa: E402

TARGETS = {
    "CN_TSF_TOTAL": "CN_TSF_TOTAL_PBC_REPORTED_CANDIDATE",
    "CN_GOV_BOND_FINANCING": "CN_GOV_BOND_FINANCING_PBC_REPORTED_CANDIDATE",
}
DATES = pd.date_range("2026-04-30", "2026-07-31", freq="ME")


def load_candidate(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"series_id", "date", "value", "unit", "frequency", "source", "source_url"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"candidate missing columns: {sorted(missing)}")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    return frame


def validate(canonical: pd.DataFrame, candidate: pd.DataFrame) -> pd.DataFrame:
    if set(candidate["series_id"]) != set(TARGETS.values()):
        raise ValueError("candidate IDs are not exactly the two PBC reported IDs")
    rows = []
    for production, candidate_id in TARGETS.items():
        c = candidate[candidate.series_id.eq(candidate_id)].copy()
        if len(c) != 4 or set(c.date) != set(DATES) or c.date.duplicated().any():
            raise ValueError(f"{candidate_id} must contain exactly 2026-04..07 month ends")
        if not c.unit.eq("bn_cny").all() or not c.frequency.eq("monthly").all():
            raise ValueError(f"{candidate_id} has invalid unit/frequency")
        if not c.source.eq("PBC").all() or not c.source_url.str.startswith("https://www.pbc.gov.cn/").all():
            raise ValueError(f"{candidate_id} lacks PBC provenance")
        old = canonical[canonical.series_id.eq(production)].copy()
        old["date"] = pd.to_datetime(old.date)
        hist = old[old.date.le("2026-03-31")]
        if hist.empty or hist.date.max() != pd.Timestamp("2026-03-31"):
            raise ValueError(f"{production} history does not end at 2026-03-31")
        wind = canonical[canonical.series_id.eq(production + "_WIND_CANDIDATE")].copy()
        wind["date"] = pd.to_datetime(wind.date)
        wind = wind[wind.date.isin(DATES)].set_index("date")
        joined = c.set_index("date").join(wind[["value"]].rename(columns={"value": "wind_value"}), how="left")
        if joined.wind_value.isna().any():
            raise ValueError(f"{production} Wind reconciliation is incomplete")
        absolute = (joined.value - joined.wind_value).abs()
        if not (absolute <= 10.0).all():
            raise ValueError(f"{production} fails Wind reconciliation: max diff={absolute.max()}")
        rows.append({"series_id": production, "rows": 4, "max_wind_diff_bn_cny": float(absolute.max())})
    return pd.DataFrame(rows)


def apply(canonical_path: Path, db_path: Path, candidate_path: Path, backup_dir: Path) -> dict:
    canonical = pd.read_parquet(canonical_path)
    candidate = load_candidate(candidate_path)
    checks = validate(canonical, candidate)
    backup_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(canonical_path, backup_dir / "macro.parquet")
    if db_path.exists():
        shutil.copy2(db_path, backup_dir / "macro.duckdb")
    try:
        replacements = []
        for production, candidate_id in TARGETS.items():
            c = candidate[candidate.series_id.eq(candidate_id)].copy()
            c["series_id"] = production
            c["series_name"] = production
            c["category"] = "macro"
            c["source_file"] = candidate_path.name
            c["import_time"] = pd.Timestamp.now()
            c["file_hash"] = ""
            # Keep report-level provenance in canonical rows for auditability.
            replacements.append(c)
        replacement = pd.concat(replacements, ignore_index=True)
        dates = pd.to_datetime(canonical.date)
        keep = ~(canonical.series_id.isin(TARGETS) & dates.isin(DATES))
        merged = pd.concat([canonical.loc[keep], replacement], ignore_index=True)
        merged["date"] = pd.to_datetime(merged.date)
        merged = merged.sort_values(["series_id", "date"]).reset_index(drop=True)
        tmp = canonical_path.with_suffix(".pbc_tail.tmp.parquet")
        merged.to_parquet(tmp, index=False)
        tmp.replace(canonical_path)
        counts = rebuild_duckdb_from_canonical(load_indicator_config(paths.INDICATORS_YAML), db_path=db_path)
    except Exception:
        shutil.copy2(backup_dir / "macro.parquet", canonical_path)
        if (backup_dir / "macro.duckdb").exists():
            shutil.copy2(backup_dir / "macro.duckdb", db_path)
        raise
    return {"backup_dir": str(backup_dir), "checks": checks.to_dict(orient="records"), "duckdb": counts}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--candidate", type=Path, default=paths.LOCAL_DIR / "pbc_reported_flow_candidates_20260831.csv")
    args = ap.parse_args()
    canonical_path, db_path = paths.MACRO_PARQUET, paths.DUCKDB_PATH
    canonical = pd.read_parquet(canonical_path)
    candidate = load_candidate(args.candidate)
    checks = validate(canonical, candidate)
    print(checks.to_string(index=False))
    if not args.apply:
        print("DRY-RUN: no files changed")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = apply(canonical_path, db_path, args.candidate, ROOT / "data" / "local" / f"pbc_tail_backup_{stamp}")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
